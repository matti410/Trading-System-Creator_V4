// Fa girare uno script Pine (v5/v6) con PineTS sulle barre di un CSV del
// progetto e salva i valori dei plot in un CSV, una riga per barra.
//
// Uso (dalla cartella strumenti_pinets):
//     node esegui_pine.mjs <dati.csv> <script.pine> <uscita.csv>
//
// Il CSV in ingresso ha le colonne Date, Open, High, Low, Close, Volume (come
// i file di dati/). Serve SOLO come strumento di collaudo (test di fedelta'
// a TradingView, docs/51 §4): PineTS e' AGPL-3.0 e non entra nel progetto.
import { readFileSync, writeFileSync } from 'node:fs';
import { PineTS } from 'pinets';

const [, , fileDati, filePine, fileUscita] = process.argv;
if (!fileUscita) {
    console.error('uso: node esegui_pine.mjs <dati.csv> <script.pine> <uscita.csv>');
    process.exit(1);
}

const righe = readFileSync(fileDati, 'utf8').trim().split(/\r?\n/);
const testa = righe[0].split(',');
const col = (nome) => testa.indexOf(nome);
const [iD, iO, iH, iL, iC, iV] = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume'].map(col);
const candele = righe.slice(1).map((r) => {
    const c = r.split(',');
    const t = Date.parse(c[iD].replace(' ', 'T') + (c[iD].includes('+') || c[iD].endsWith('Z') ? '' : 'Z'));
    return {
        openTime: t, closeTime: t + 1,
        open: +c[iO], high: +c[iH], low: +c[iL], close: +c[iC], volume: +c[iV],
    };
});

const pine = readFileSync(filePine, 'utf8');
const pineTS = new PineTS(candele);
const { plots } = await pineTS.run(pine);

const nomi = Object.keys(plots);
const n = candele.length;
const fuori = ['Date,' + nomi.join(',')];
for (let i = 0; i < n; i++) {
    const valori = nomi.map((k) => {
        const v = plots[k].data[i];
        const x = v && typeof v === 'object' ? v.value : v;
        return x === null || x === undefined || Number.isNaN(x) ? '' : String(x);
    });
    fuori.push(righe[i + 1].split(',')[iD] + ',' + valori.join(','));
}
writeFileSync(fileUscita, fuori.join('\n'));
console.log(`PineTS: ${n} barre, plot: ${nomi.join(', ')}`);
