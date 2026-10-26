"""
Suite del riordino della pipeline, parte Lab (25/10/2026, docs/68 §11.1, PR B):
le schermate 2-4 riordinate di engine/vetrina.py su un perpetual sintetico
aperto 24 ore su 24, con due trigger costruiti apposta (T_FORTE long e
T_FORTE_S short: dopo ogni segnale il prezzo va nel verso del trade).

    A · prepara e il registro del dataset (§9.1): H diverso sullo stesso
        dataset = conto ripreso e risalita segnalata; stesso H = niente; confine
        spostato = da zero; la soglia con due H usa le prove equivalenti
    B · 2a, 2c, 3a: riga delle prove, curve dello scarto, casistiche suggerite,
        classifica a scomparsa con la barra del picco (§2, §8)
    C · 3b, le casistiche dalla rosa (§4): rosa - togli + aggiungi, nomi
        sbagliati, nessuna prova in piu'; un trigger a orario porta le fasce
    D · 4, le uscite consigliate (§5): barre = H qualunque sia il picco, stop 90,
        target spento; il conto delle impostazioni; trigger a orario: X_ORA_@ =
        ingresso + H barre, stessi trade
    E · la cella nella casistica (§3.3): entry «TRIGGER+CELLA_…» = AND delle
        maschere, uscite sulla casistica, passo 5 strada B senza prove in piu'
    F · 4b -> passo 5 (§7): «Solo long» spegne lo short al passo 5
    G · il diario dell'out-of-sample e le risalite (§9); la riga delle prove
        della schermata 4 e la scheda dicono lo stesso numero
    H · il Lab piu' chiaro (26/10/2026, docs/73 §A.5): il campo «parti da»
        della 3b, la regola della 3d (qualunque situazione misurata, anche in
        OR, sotto le 200 occasioni no), i nomi in chiaro delle situazioni

Si lancia da terminale, dalla cartella del progetto:

    python test_riordino_lab.py

(su Windows: PYTHONIOENCODING=utf-8). Non serve MT5 ne' alcun file di dati.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import warnings

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

import engine.exchange as X
from engine import registro_dataset as rd
from engine import registry as reg
from engine import vetrina as vt
from engine.giudizio import prove_trigger_orizzonti, soglia_rumore
from engine.quarantena import imposta_rollover
from test_atlante import H, Mercato, _deriva_dopo, _indice, _registra_entry

SYMBOL = "BINANCE_PERP_BTCUSDT"


def _muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def _parlato(f, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = f(*a, **k)
    return r, buf.getvalue()


def esegui() -> int:
    ESITI: list[bool] = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        print(f"  [{'OK  ' if condizione else 'FAIL'}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def errore(f, testo):
        try:
            _muto(f)
        except ValueError as e:
            return testo in str(e)
        return False

    imposta_rollover(None)
    rd.azzera()
    # il mercato: random walk 24/7 con due trigger che portano un movimento noto
    M = Mercato(_indice(giorni=300), seme=11)
    n = len(M.idx)
    rng = np.random.default_rng(5)
    # long nei giorni pari, short nei dispari: guadagni giornalieri non legati, la rosa li tiene tutti e due
    giorno = (np.arange(n) // 96) % 2
    adatte = np.arange(600, n - 50, 4)
    pos_l = np.sort(rng.choice(adatte[giorno[adatte] == 0], size=1500, replace=False))
    pos_s = np.sort(rng.choice(adatte[giorno[adatte] == 1], size=1500, replace=False))
    extra = _deriva_dopo(n, pos_l, np.full(pos_l.size, 0.0002)) + _deriva_dopo(n, pos_s, np.full(pos_s.size, -0.0002))
    d = M.df(extra)
    d[["Open", "High", "Low", "Close"]] *= 100.0
    _registra_entry("T_FORTE", 1, M.idx[pos_l])
    _registra_entry("T_FORTE_S", -1, M.idx[pos_s])
    orari = pd.date_range(d.index[0].floor("8h"), d.index[-1].ceil("8h"), freq="8h")
    fund = X.con_intervalli(pd.DataFrame({"tasso": 0.0001}, index=orari))

    with tempfile.TemporaryDirectory() as tmp:
        X.salva_csv(d, os.path.join(tmp, f"{SYMBOL}_M15.csv"))
        X.salva_funding(fund, X.file_funding(SYMBOL, tmp))

        # =============================================================== A ==
        print("\nA · PREPARA E IL REGISTRO DEL DATASET\n" + "-" * 70)
        s = _muto(vt.prepara, SYMBOL, H=H, cartella=tmp)
        s.prove["trigger"] = 50                                   # un conto qualsiasi, da ritrovare
        s_b, testo_b = _parlato(vt.prepara, SYMBOL, H=6, cartella=tmp)
        check("A1. stesso dataset, H = 6 dopo H = 8: conto ripreso, H provati [8, 6], risalita segnalata",
              s_b.prove is s.prove and s_b.storia.h_provati == [8, 6] and "Hai già lavorato su questo dataset con H = 8"
              in testo_b and s_b.storia.risalite[-1]["da"] == 8)
        s_c, testo_c = _parlato(vt.prepara, SYMBOL, H=6, cartella=tmp)
        check("A2. di nuovo H = 6: nessuna segnalazione, nessun H in piu'",
              "Hai già lavorato" not in testo_c and s_c.storia.h_provati == [8, 6] and len(s_c.storia.risalite) == 1)
        conti = vt._soglia_cumulata_lab(s_c, np.nan)
        atteso = prove_trigger_orizzonti(50, [8, 6])
        per = 1 - (1 - 0.05) ** (1 / atteso)
        from statistics import NormalDist
        check("A3. la soglia con due H: la voce dei trigger e' il numero equivalente, la soglia Šidák su quel numero",
              abs(conti["voce_trigger"] - atteso) < 1e-9 and 50 < atteso < 100
              and abs(conti["soglia"] - NormalDist().inv_cdf(1 - per / 2)) < 1e-12
              and "2 orizzonti provati" in conti["frase"], f"50 trigger con H = 8 e 6: {atteso:.1f} prove")
        s_d, testo_d = _parlato(vt.prepara, SYMBOL, H=H, cartella=tmp, quota_in_sample=0.7)
        check("A4. confine dell'in-sample spostato: dataset diverso, conto da zero, e lo scrive",
              s_d.prove["trigger"] == 0 and s_d.storia.h_provati == [H] and "Dataset diverso" in testo_d
              and vt._soglia_cumulata_lab(s_d, np.nan)["k"] == 0)
        rd.azzera()
        s = _muto(vt.prepara, SYMBOL, H=H, cartella=tmp)
        check("A5. con un H solo il conto e' quello di prima: k intero, soglia_rumore(k)",
              vt._soglia_cumulata_lab(s, np.nan)["k"] == 0 and vt._soglia_sidak(17) == soglia_rumore(17))

        # =============================================================== B ==
        print("\nB · 2a, 2c, 3a\n" + "-" * 70)
        _, t2a = _parlato(vt.profilo_delle_ore, s)
        _, t2c = _parlato(vt.esplora, s)
        k = len(s.ev.sintesi)
        check("B1. 2a prima delle curve: riga delle prove senza prove; 2c: «k trigger misurati» e le curve",
              "Prove · questa schermata: nessuna" in t2a and f"Prove · questa schermata: {k} trigger misurati" in t2c
              and s.curve_scarto is not None and "T_FORTE" in s.curve_scarto.columns
              and list(s.curve_scarto.index) == list(range(1, H + 1)))
        r = s.rosa_trigger.set_index("candidato")
        check("B2. a k = H la curva della 2c coincide con lo scarto della rosa (stesso metro)",
              abs(s.curve_scarto.loc[H, "T_FORTE"] - r.loc["T_FORTE", "scarto_bp"]) < 1e-9)
        _, t3a = _parlato(vt.rosa_dei_trigger, s)
        sugg = s.tabelle["casistiche_suggerite"]
        cl = s.tabelle["classifiche_rosa"]
        # un long e uno short che scattano spesso hanno guadagni giornalieri legati (il mercato li muove in
        # versi opposti): la rosa ne tiene uno, e l'altro resta fuori «correlato». Basta che ce ne sia uno
        check("B3. 3a: T_FORTE o T_FORTE_S fra le casistiche suggerite; classifica a scomparsa con la barra del "
              "picco, ordinata per solidita' netta; nessuna prova in piu'",
              ("T_FORTE" in sugg["long"] or "T_FORTE_S" in sugg["short"]) and "[dettaglio] La classifica" in t3a
              and "Barra del picco (solo da leggere)" in cl["Classifica LONG"].columns
              and cl["Classifica LONG"]["Solidità netta"].is_monotonic_decreasing
              and "Prove · questa schermata: nessuna" in t3a, f"long {sugg['long']} · short {sugg['short']}")

        # =============================================================== C ==
        print("\nC · 3b, LE CASISTICHE DALLA ROSA\n" + "-" * 70)
        prima = {k_: (dict(v) if isinstance(v, dict) else v) for k_, v in s.prove.items()}
        tab = _muto(vt.scegli_casistiche, s)
        check("C1. campi vuoti = la rosa cosi' com'e', con da dove viene ogni trigger; nessuna prova in piu'",
              s.trigger_long == tuple(sugg["long"]) and s.trigger_short == tuple(sugg["short"])
              and all(v == "rosa" for c_ in s.casistiche.values() for v in c_["origine"].values())
              and {k_: (dict(v) if isinstance(v, dict) else v) for k_, v in s.prove.items()} == prima
              and "Da dove" in tab.columns)
        def solo_forti():
            _muto(vt.scegli_casistiche, s, togli_long=", ".join(sugg["long"]), aggiungi_long="T_FORTE",
                  togli_short=", ".join(sugg["short"]), aggiungi_short="T_FORTE_S")
        solo_forti()
        check("C2. togli tutta la rosa e aggiungi: long = T_FORTE, short = T_FORTE_S, «aggiunta» anche se erano in rosa",
              s.trigger_long == ("T_FORTE",) and s.trigger_short == ("T_FORTE_S",)
              and s.casistiche["short"]["origine"]["T_FORTE_S"] == "aggiunta"
              and s.casistiche["long"]["origine"]["T_FORTE"] == "aggiunta")
        cat_l = [x for x in vt._trigger_candidati(1) if x not in sugg["long"]][0]
        check("C3. nomi sbagliati: togli fuori dalla rosa, aggiungi fuori dal catalogo o del lato sbagliato",
              errore(lambda: vt.scegli_casistiche(s, togli_long=cat_l), "non è fra le casistiche suggerite")
              and errore(lambda: vt.scegli_casistiche(s, aggiungi_long="NON_ESISTE"), "non è un trigger long")
              and errore(lambda: vt.scegli_casistiche(s, aggiungi_long="T_FORTE_S"), "non è un trigger long")
              and errore(lambda: vt.scegli_casistiche(s, aggiungi_short="ORA_LONG_@10:00"), "non è un trigger short")
              and errore(lambda: vt.scegli_casistiche(s, togli_long=", ".join(sugg["long"]),
                                                      togli_short=", ".join(sugg["short"])), "Nessuna casistica"))
        _muto(vt.scegli_casistiche, s, togli_long=", ".join(sugg["long"]), aggiungi_long="ORA_LONG_@10:00",
              togli_short=", ".join(sugg["short"]))
        check("C4. un trigger a orario aggiunto porta le 96 fasce del profilo",
              s.trigger_long == ("ORA_LONG_@10:00",) and s.prove.get("fasce") == 96)

        # =============================================================== D ==
        print("\nD · 4, LE USCITE CONSIGLIATE\n" + "-" * 70)
        uscite_prima = len(s.prove["uscite"])
        _, t4 = _parlato(vt.imposta_uscite, s, regola_uscita="consigliata")
        c = s.consigliate["long"]
        check("D1. trigger a orario: barre = H, stop 90, target spento, regola X_ORA_@ = 10:00 + H barre da 15 minuti",
              (c["barre"], c["sl"], c["tp"], c["regola"]) == (H, 90.0, 0.0, "X_ORA_@12:00")
              and s.uscite["regola"] == "X_ORA_@12:00" and s.uscite["n_barre_long"] == H)
        tr_ora = s.es.trades(s.es.risultati.iloc[0]["combinazione"])
        _muto(vt.imposta_uscite, s, regola_uscita="nessuna")
        tr_tempo = s.es.trades(s.es.risultati.iloc[0]["combinazione"])
        col = ["EntryTime", "ExitTime", "EntryPrice", "ExitPrice"]
        check("D2. stessi trade con l'uscita a orario e con la scadenza a H barre",
              len(tr_ora) > 100 and tr_ora[col].reset_index(drop=True).equals(tr_tempo[col].reset_index(drop=True)),
              f"{len(tr_ora)} trade")
        solo_forti()
        n0 = len(s.prove["uscite"])
        _, t4 = _parlato(vt.imposta_uscite, s, regola_uscita="consigliata")
        picco = s.consigliate["long"]["picco"]
        check("D3. consigliate per T_FORTE: barre = H qualunque sia il picco, il picco solo da leggere nella tabella",
              s.consigliate["long"]["barre"] == H and s.uscite["n_barre_long"] == H and s.uscite["perc_sl"] == 90.0
              and s.uscite["perc_tp"] == 0.0 and s.uscite["regola"] is None
              and "consigliate" in set(s.tabelle["uscite_consigliate"]["Quali"])
              and "con le uscite consigliate" in t4, f"picco alla barra {picco['barra']} di {H}")
        _, t4b = _parlato(vt.imposta_uscite, s, regola_uscita="consigliata")
        n1 = len(s.prove["uscite"])
        barre_picco = int(picco["barra"]) if picco["barra"] != H else H - 1
        _, t4c = _parlato(vt.imposta_uscite, s, barre_long=barre_picco, regola_uscita="consigliata")
        _muto(vt.imposta_uscite, s, sl=80, regola_uscita="consigliata")
        n2 = len(s.prove["uscite"])
        check("D4. il conto: consigliata = 1 impostazione; rifatta uguale +0; barre al picco +1 («una modifica»); "
              "un altro stop +1",
              n1 == n0 + 1 and "già provate" in t4b and "una modifica" in t4c and n2 == n1 + 2,
              f"impostazioni {uscite_prima} -> {n0} -> {n1} -> {n2}")
        _muto(vt.imposta_uscite, s, barre_long=barre_picco, regola_uscita="consigliata")
        check("D5. con una modifica la tabella mostra la riga «la tua modifica» accanto a quella consigliata",
              list(s.tabelle["uscite_consigliate"]["Quali"])[:2] == ["consigliate", "la tua modifica"])

        # =============================================================== E ==
        print("\nE · LA CELLA NELLA CASISTICA\n" + "-" * 70)
        _muto(vt.atlante_dei_trigger, s)
        a = s.atlante
        riga = a[(a["candidato"] == "T_FORTE") & (a["asse"] == "sessione")].sort_values("eventi").iloc[-1]
        cella = riga["cella"]
        s.atlante.loc[(a["candidato"] == "T_FORTE") & (a["cella"] == cella), "passa"] = True   # forzata, solo qui
        prove_filtri = dict(s.prove["filtri"])
        _muto(vt.scegli_cella, s, long=cella)
        nome = f"T_FORTE+CELLA_{cella}_L"
        m_der = reg.get_entry(nome)(s.df_is).to_numpy(dtype=bool)
        m_and = (reg.get_entry("T_FORTE")(s.df_is).to_numpy(dtype=bool)
                 & reg.get_filter(f"CELLA_{cella}_L")(s.df_is).to_numpy(dtype=bool))
        check("E1. l'entry della casistica e' «T_FORTE+CELLA_…_L», vera dove sono veri trigger e cella",
              s.entry_casistica_long == nome and np.array_equal(m_der, m_and) and m_der.sum() < reg.get_entry(
                  "T_FORTE")(s.df_is).sum() and s.casistiche["long"]["cella"] == cella and s.uscite is None,
              f"cella {cella}: {int(m_der.sum())} segnali")
        _muto(vt.imposta_uscite, s, regola_uscita="consigliata")
        r_es = s.es.risultati
        solo_l = r_es[(r_es["entry_long"] == nome) & r_es["entry_short"].isna()]
        check("E2. le uscite lavorano sulla casistica con la cella: l'entry long di ogni sistema e' quella con la "
              "cella, e «Solo long» non ha piu' trade dei segnali dentro la cella",
              set(r_es["entry_long"].dropna()) == {nome} and len(solo_l) == 1
              and 0 < int(solo_l["trades"].iat[0]) <= int(m_der.sum()), f"{int(solo_l['trades'].iat[0])} trade")
        _muto(vt.rosa_dei_sistemi, s)
        _muto(vt.trova_strategia, s)
        check("E3. passo 5 strada B: trigger senza cella contro la cella, nessuna prova in piu'",
              s.fs.entry_long == s.entry_long == "T_FORTE" and dict(s.prove["filtri"]) == prove_filtri
              and any(f.startswith("CELLA_") for f in s.fs.risultati["filtro"]))
        _muto(vt.scegli_cella, s)
        check("E4. senza cella si torna al trigger da solo (e le uscite vanno rifatte)",
              s.entry_casistica_long == "T_FORTE" and s.uscite is None and s.casistiche["long"]["cella"] is None)

        # =============================================================== F ==
        print("\nF · 4b -> PASSO 5\n" + "-" * 70)
        _muto(vt.imposta_uscite, s, regola_uscita="consigliata")
        _muto(vt.rosa_dei_sistemi, s)
        check("F1. predefinito con i due lati: «Long + Short»", s.sistema == "Long + Short")
        _muto(vt.rosa_dei_sistemi, s, sistema="Solo long")
        _muto(vt.trova_strategia, s)
        check("F2. «Solo long» alla 4b: il passo 5 gira con lo short spento",
              s.fs.entry_long == "T_FORTE" and s.fs.entry_short is None)
        check("F3. un sistema che non c'e' si ferma", errore(lambda: vt.rosa_dei_sistemi(s, sistema="Solo lungo"),
                                                              "non provato"))

        # =============================================================== G ==
        print("\nG · IL DIARIO DELL'OUT-OF-SAMPLE E LE RISALITE\n" + "-" * 70)
        _muto(vt.scheda, s, None)
        k_scheda = s.tabelle["soglia_cumulata"]["k"]
        check("G1. la scheda apre l'out-of-sample una volta; la riga delle prove e la scheda dicono lo stesso numero",
              len(s.storia.diario) == 1 and _muto(vt._riga_prove, s, "x")["k"] == k_scheda, f"k = {k_scheda}")
        _, t_ris = _parlato(vt.scegli_casistiche, s, togli_long=", ".join(sugg["long"]), aggiungi_long="T_FORTE",
                            togli_short=", ".join(sugg["short"]))
        check("G2. dopo la scheda, cambiare le casistiche: riquadro arancione e risalita annotata",
              "[ATTENZIONE] Hai già guardato l'out-of-sample" in t_ris
              and s.storia.risalite[-1]["cosa"] == "casistiche" and s.storia.risalite[-1]["oos_visto"])
        _muto(vt.imposta_uscite, s, regola_uscita="consigliata")
        _muto(vt.rosa_dei_sistemi, s)
        _muto(vt.trova_strategia, s)
        _, t_sch = _parlato(vt.scheda, s, None)
        check("G3. la seconda scheda: «già guardato 2 volte», con le scelte cambiate dopo la prima",
              len(s.storia.diario) == 2 and "Out-of-sample già guardato 2 volte" in t_sch
              and "casistiche short" in t_sch)
        _, t_h = _parlato(vt.prepara, SYMBOL, H=6, cartella=tmp)
        check("G4. cambiare H dopo l'out-of-sample: lo dice, e il diario resta",
              "Hai anche già guardato l'out-of-sample (2 volte)" in t_h
              and len(rd.storia(SYMBOL, "M15", s.df_is.index[-1]).diario) == 2)

        # =============================================================== H ==
        print("\nH · LAB PIU' CHIARO (docs/73 §A.5): 3b «PARTI DA», 3d QUALUNQUE SITUAZIONE MISURATA\n" + "-" * 70)
        from engine.atlante import CELLE, NOMI_IN_CHIARO, nome_in_chiaro
        r = s.rosa_trigger
        prove_h = {k_: (dict(v) if isinstance(v, dict) else v) for k_, v in s.prove.items()}
        _muto(vt.scegli_casistiche, s)
        da_rosa = (s.trigger_long, s.trigger_short)
        tab_r = _muto(vt.scegli_casistiche, s, parti_da="la rosa")
        uguale_rosa = (s.trigger_long, s.trigger_short) == da_rosa
        tab_c = _muto(vt.scegli_casistiche, s, parti_da="tutte le candidate")
        cand = {d: list(r.loc[r["candidata"].astype(bool) & (r["direction"] == d), "candidato"]) for d in (1, -1)}
        _muto(vt.scegli_casistiche, s, parti_da="niente", aggiungi_long="T_FORTE")
        niente = (s.trigger_long, s.trigger_short, s.casistiche["long"]["origine"]["T_FORTE"])
        check("H1. «parti da»: la rosa = come prima (predefinito); tutte le candidate = tutte e sole le candidate "
              "del lato; niente = solo «aggiungi»; la tabella dice da dove si parte; nessuna prova in piu'",
              uguale_rosa and list(s.tabelle["casistiche"]["Parti da"]) == ["niente", "niente"]
              and list(tab_r["Parti da"]) == ["la rosa", "la rosa"]
              and list(tab_c["Parti da"]) == ["tutte le candidate", "tutte le candidate"]
              and niente == (("T_FORTE",), (), "aggiunta")
              and {k_: (dict(v) if isinstance(v, dict) else v) for k_, v in s.prove.items()} == prove_h,
              f"candidate long {cand[1]} · short {cand[-1]}")
        check("H2. «niente» con «togli» pieno si ferma; un punto di partenza sconosciuto si ferma; partendo da "
              "niente senza aggiungere si ferma",
              errore(lambda: vt.scegli_casistiche(s, parti_da="niente", togli_long="T_FORTE"), "non c'è niente da togliere")
              and errore(lambda: vt.scegli_casistiche(s, parti_da="tutto"), "«parti da» non valido")
              and errore(lambda: vt.scegli_casistiche(s, parti_da="niente"), "Nessuna casistica"))
        rosa_mano = pd.DataFrame({
            "candidato": ["A", "B", "C", "D"], "direction": [1, 1, 1, -1],
            "candidata": [True, True, False, True], "nella_rosa": [True, False, False, True],
            "perche": ["", "famiglia già nella rosa (A)", "non fa meglio del mercato", ""]})
        nomi_c, orig_c = vt.casistiche_dalla_rosa(rosa_mano, 1, parti_da="candidate")
        nomi_r, _ = vt.casistiche_dalla_rosa(rosa_mano, 1)
        nomi_n, _ = vt.casistiche_dalla_rosa(rosa_mano, 1, parti_da="niente")
        check("H3. casistiche_dalla_rosa (anche per il notebook di ricerca): candidate = A e B, con il motivo della "
              "rosa in «da dove»; rosa = A; niente = nessuna; «togli» controllato sul punto di partenza",
              nomi_c == ["A", "B"] and orig_c == {"A": "rosa", "B": "candidata, fuori dalla rosa: famiglia già nella "
                                                                       "rosa (A)"}
              and nomi_r == ["A"] and nomi_n == []
              and errore(lambda: vt.casistiche_dalla_rosa(rosa_mano, 1, togli="C", parti_da="candidate"),
                         "non è fra le candidate della rosa")
              and vt.casistiche_dalla_rosa(rosa_mano, 1, togli="B", parti_da="candidate")[0] == ["A"])
        atl = pd.DataFrame({"candidato": ["T1", "T2", "T1"], "cella": ["EUROPA", "EUROPA", "AMERICA"],
                            "eventi": [199, 200, 500], "misurata": [False, True, True],
                            "passa": [False, False, True], "motivo": ["troppo pochi casi", "non paga i costi", ""]})
        atl.attrs["min_eventi"] = 200
        due = vt.controlla_cella(atl, ["T1", "T2"], "EUROPA", "long")
        passa = vt.controlla_cella(atl, "T1", "AMERICA", "long")
        check("H4. regola della 3d: 199 occasioni si ferma (con le occasioni e l'elenco delle misurate); con due "
              "trigger in OR basta che uno la misuri (200 occasioni) e, se non passa, c'e' l'avviso con il motivo; "
              "una situazione che passa non ha avviso",
              errore(lambda: vt.controlla_cella(atl, "T1", "EUROPA", "long"), "199 per T1")
              and errore(lambda: vt.controlla_cella(atl, "T1", "EUROPA", "long"), "non si può scegliere")
              and errore(lambda: vt.controlla_cella(atl, "T1", "EUROPA", "long"), "AMERICA")
              and not due["passa"] and due["avviso"].startswith(vt.AVVISO_CELLA_NON_PASSA)
              and "T2: non paga i costi" in due["avviso"]
              and passa["passa"] and passa["avviso"] is None
              and errore(lambda: vt.controlla_cella(atl, "T1", "VOL_ALTA", "long"), "sconosciuta"))
        check("H5. l'atlante misura una situazione se e solo se ha almeno 200 occasioni (la regola che la 3d usa)",
              bool(((s.atlante["eventi"] >= vt.MIN_TRIGGER) == s.atlante["misurata"].astype(bool)).all()))
        tutte = [c for nomi in CELLE.values() for c in nomi]
        check("H6. i nomi in chiaro coprono tutte le situazioni dell'atlante, tutti diversi",
              set(NOMI_IN_CHIARO) == set(tutte) and len(set(map(nome_in_chiaro, tutte))) == len(tutte)
              and nome_in_chiaro("NON_ESISTE") == "NON_ESISTE")
    reg.clear_registry()
    rd.azzera()

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
