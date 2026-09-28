# Analisi: quanto errore sull'HRV toglie l'SQI dell'app, e quanti dati costa?

Due dataset: dito in laboratorio (PTT-PPG, §3–7) e fronte nella vita reale (WildPPG, §8).

Tutti i numeri qui sotto vengono da `results/summary.json`, `results/sweep.csv` e
`results/fiducial_check.json`, prodotti da `reproduce.sh`. L'intera catena è stata eseguita due volte
e ha dato risultati identici bit per bit (hash SHA-256 in fondo).

## 1. Cosa c'è in questa cartella

| File | Contenuto |
|---|---|
| `app_pipeline.py` | Porting Python riga per riga di `lib/processing/` + ordine delle operazioni di `home_page.dart`. `fs` è un parametro ovunque. |
| `dart_ref/ref.dart`, `dart_ref/gen_reference.py` | Eseguono le **classi Dart originali dell'app** (importate in sola lettura) su segnali sintetici e salvano gli output in `dart_ref/out/`. |
| `synthetic.py` | Segnali sintetici con seed fisso (NON sono dati reali). |
| `tests/test_ecg_and_options.py` | 3 test: rilevatore R su ECG sintetico, pulizia RR con battito perso, opzione `record_sqi` che non cambia i picchi. |
| `tests/test_port.py` | 27 test: equivalenza con il Dart, coefficienti del filtro = `scipy.signal.butter`, −3 dB ai tagli, RMSSD, arrotondamento Dart, recupero di HR/RMSSD su sintetico, SQI = 0 a sensore staccato, gate > 0,4 che non si avvia. |
| `load_ptt.py`, `download_ptt_ppg.sh` | Download (verificato SHA-256) e lettura del dataset. |
| `run_analysis.py` | Analisi principale. |
| `fiducial_check.py` | Dove cadono i picchi dell'app rispetto all'onda R. |
| `make_figure.py` | La figura del brief. |
| `check_terra_schema.sh` | Verifica dei campi di qualità nello schema OpenAPI pubblico di Terra. |
| `ecg_rpeaks.py`, `validate_rpeaks.py` | Rilevatore di picchi R (per WildPPG, che non ha annotazioni) e sua validazione sui picchi manuali di PTT-PPG a 128 Hz. |
| `load_wildppg.py`, `download_wildppg.sh` | Download da polybox ETH, estrazione dei canali usati, cancellazione del grezzo. |
| `run_wildppg.py`, `wildppg_channel_check.py` | Analisi alla fronte (WildPPG) e controllo canale IR/verde. |
| `reproduce.sh` | Rifà tutto da zero. |
| `results/` | Output (CSV, JSON, figura, log). |

## 2. Verifica del porting

`tests/test_port.py` confronta il porting con l'output delle classi Dart originali su 5 segnali
sintetici (100, 64 e 125 Hz; pulito, con artefatti di movimento, sensore staccato), sia con gate SQI
0,4 sia senza gate. Filtrato (tolleranza 1e-9), picchi (identici), SQI per campione (1e-12), RMSSD a
1 Hz, numero di intervalli nel buffer e buffer RR finale coincidono. Esito, con gli altri 3 test: **30 passed**
(`results/pytest_output.txt`).

L'ordine delle operazioni per pacchetto (`home_page.dart:151-199`) è una mia trascrizione, perché
`home_page.dart` dipende da Flutter e non si può eseguire fuori dall'app. Le classi di `processing/`
invece girano senza modifiche.

## 3. Scelta del dataset

Controllato il 2026-09-28:

| Candidato | Dimensione / accesso / licenza (verificati) | PPG | Scelto? |
|---|---|---|---|
| WESAD | zip 2,25 GB (header HTTP), link pubblico senza registrazione | BVP dell'Empatica E4 al polso, 64 Hz | no |
| PPG-DaLiA | zip 2,87 GB (pagina UCI), CC BY 4.0, senza registrazione | BVP dell'Empatica E4 al polso, 64 Hz | no (download avviato e interrotto, file parziale cancellato) |
| TROIKA (IEEE SPC 2015) | non verificato | PPG da polso, 125 Hz, corsa su tapis roulant | no |
| **PhysioNet Pulse Transit Time PPG v1.1.0** | 2,9 GB in totale ma solo ~410 MB nel formato WFDB usato qui; **ODbL 1.0**, accesso aperto senza login | **MAX30101 grezzo** (IR/Red/Green, con componente DC), 500 Hz | **sì** |

Motivo. L'SQI dell'app ha un termine di ampiezza che divide per la componente DC del grezzo. Il BVP
dell'E4 (WESAD, DaLiA) è distribuito già elaborato e centrato attorno allo zero, quindi quel termine
non avrebbe senso. Questo si basa sulla documentazione nota dell'E4 e **non** è stato verificato
scaricando quei dati. PTT-PPG usa invece **lo stesso chip degli occhiali** (MAX30101), fornisce il
segnale grezzo con DC nella stessa polarità che riceve l'app (verificato: la luce ha il massimo ~180 ms
dopo l'onda R, cioè sul piede dell'onda, e cala in sistole), ha ECG sincrono con picchi R annotati
(rilevati automaticamente e verificati a mano dagli autori) e accelerometro. 22 soggetti, 3 attività
(seduto, cammino sul posto, corsa), circa 8,5 minuti per registrazione.

Riferimento: Mehrgardt P., Khushi M., Poon S., Withana A. *Pulse Transit Time PPG Dataset* (v1.1.0).
PhysioNet, 2022. https://doi.org/10.13026/jpan-6n92

### Se si vuole usare WESAD o PPG-DaLiA a mano

- PPG-DaLiA: https://archive.ics.uci.edu/dataset/495/ppg+dalia → "Download" (2,87 GB). Lo zip contiene
  a sua volta `data.zip` con un file `SX/SX.pkl` per soggetto: `signal['wrist']['BVP']` (64 Hz),
  `signal['chest']['ECG']` (700 Hz), `signal['wrist']['ACC']`.
- WESAD: `curl -L -o WESAD.zip https://uni-siegen.sciebo.de/s/HGdUkoNlW1Ub0Gx/download` (2,25 GB). Stessa
  struttura `SX/SX.pkl`. Prima dell'uso va controllata la licenza nel readme.
- In entrambi i casi il termine di ampiezza dell'SQI non è applicabile così com'è: andrebbe testata
  solo la periodicità, oppure servirebbe un'altra definizione di ampiezza.

## 4. Metodo

- **Input**: `pleth_1` (IR, sensore 1), convertito in nA (×16384/2¹⁸; conta solo per la soglia di
  presenza di 10 nA) e decimato da 500 a 100 Hz (FIR a fase zero), come negli occhiali. Nessun valore
  mancante nei canali PPG usati.
- **Pipeline**: `app_pipeline.run_session`, identica all'app. Due modalità:
  - *senza gate*: `goodQuality` sempre vero; l'SQI viene calcolato ogni secondo, come nell'app;
  - *gate nel ciclo* come nell'app (`goodQuality = SQI ≥ g` a ogni battito), con g = 0,2 / 0,3 / 0,4.
- **Finestre**: 60 s non sovrapposte a partire da t = 10 s (per il warm-up del filtro): **491 finestre**,
  tutte con riferimento ECG valido.
- **Riferimento**: RR dai picchi R annotati; RR fuori da 300–2000 ms esclusi; differenze successive
  solo tra RR adiacenti validi; almeno 20 RR.
- **RMSSD da PPG**: formula dell'app (`computeRmssd`) sugli intervalli accettati dall'app che si chiudono
  nella finestra; almeno 10 intervalli, altrimenti la finestra è "non calcolabile".
- **Filtro SQI a livello di finestra**: SQI della finestra = mediana dei valori SQI a 1 Hz. Si tiene la
  finestra se SQI ≥ τ, per τ da 0 a 1 (passo 0,05 fino a 0,8, poi 0,01).
- **Ablazione**: SQI completo; solo ampiezza (`ampiezza × penalità`, con i suoi rifiuti); solo periodicità.
- **Copertura** = finestre tenute / 491. **Metriche**: errore assoluto mediano, errore assoluto
  percentuale mediano, Pearson e Spearman, Bland-Altman (bias ± 1,96 SD). **IC 95%**: bootstrap per
  soggetto (2000 ricampionamenti, seed 20260928).
- **Confronto**: filtro sull'accelerometro (deviazione standard del modulo nella finestra) a pari copertura.

## 5. Risultati

RMSSD di riferimento (ECG): mediana **22,3 ms** (IQR 16,4–30,6).

| Condizione | Finestre tenute | Errore ass. mediano (IC 95%) | Bias BA [LoA] | r |
|---|---|---|---|---|
| Pipeline dell'app, nessun filtro | 97,8% | **85,5 ms** (65,7–101,5) | +89,9 [−14,3; 194,0] | 0,11 |
| + SQI ≥ 0,4 per finestra (soglia dell'app) | 97,8% | 85,5 ms, riduzione IC [0,0; 0,0] | uguale | 0,11 |
| + SQI ≥ 0,4 nel ciclo (come l'app) | 97,8% | 85,5 ms, riduzione IC [0,00; 0,05] | +89,8 | 0,11 |
| SQI ≥ 0,96 *(post hoc)* | 66,2% | 61,2 ms (50,5–72,6) | | |
| SQI ≥ 0,97 *(post hoc)* | 40,3% | 45,8 ms (38,3–52,7) | | |
| SQI ≥ 0,98 *(post hoc, 12 soggetti)* | 10,6% | 23,7 ms (19,3–31,2) | | |
| Filtro accelerometro, stessa copertura di 0,96 / 0,97 / 0,98 | 66 / 40 / 11% | 73,9 / 57,8 / 60,3 ms | | |
| *Ipotetico, non nell'app*: segnale invertito (picco sistolico), nessun filtro | 97,4% | **18,1 ms** (10,0–34,0) | +44,1 [−65,6; 153,8] | 0,06 |
| Sensore 2 (`pleth_4`), nessun filtro | 95,7% | 110,6 ms | | −0,01 |

Per attività (pipeline dell'app, nessun filtro; tra parentesi il segnale invertito, ipotetico):
seduto 50,0 ms (4,2), cammino 101,8 ms (41,4), corsa 95,4 ms (33,2).

Osservazioni (tutte da `summary.json`):

1. **Alla soglia dell'app l'SQI non scarta nessuna finestra.** SQI completo per finestra: mediana
   0,974 da seduti, 0,962 in cammino, 0,964 in corsa (`windows.csv`). Lo stesso vale nel ciclo con
   g = 0,2, 0,3 e 0,4.
2. **Il termine di ampiezza vale 1 in tutte le 491 finestre.** La modulazione mediana è 0,35–0,49%,
   contro un punteggio pieno allo 0,02%. La penalità artefatti (> 2%) scatta nello 0,2–0,3% dei secondi.
   Tutta l'informazione dell'SQI viene dalla periodicità.
3. **L'SQI contiene un po' di segnale, ma solo tra 0,94 e 0,98.** Queste soglie sono state scelte dopo
   aver visto i dati: è una curva descrittiva, non un punto di lavoro validato. Le finestre tenute non
   hanno un'HRV vera più bassa di quelle scartate (RMSSD ECG mediano 22,9 / 25,0 / 22,4 ms tenute
   contro 21,5 / 20,2 / 22,3 ms scartate, per τ = 0,96 / 0,97 / 0,98), quindi il guadagno non viene dal
   selezionare soggetti con HRV bassa. A pari copertura l'SQI fa meglio del filtro sull'accelerometro.
4. **La fonte principale dell'errore è il punto fiduciale, non la qualità del segnale.** L'app cerca i
   massimi del grezzo, che con il MAX30101 cadono sul piede diastolico. Mediane per registrazione
   (`fiducial_check.json`): ritardo dall'onda R 193 ms con **IQR 96,8 ms**, **25,1%** dei battiti senza
   picco, 2,2% con picchi multipli. Invertendo il segnale (picco sistolico): IQR **24,0 ms**, 4,0% di
   battiti persi. Anche da seduti, con segnale pulito, l'errore mediano passa da 50,0 a 4,2 ms. Questa
   variante **non** è implementata nell'app ed è stata testata solo qui.

Figura: `results/fig_sqi_tradeoff.png` (anche `.pdf`).

## 6. Terra (schema OpenAPI pubblico)

`check_terra_schema.sh` → `results/terra_schema_check.txt`. Repository `tryterra/openapi`, commit
`9eccc73` del 2026-09-28. `HeartRateDataSample` ha `timestamp`, `bpm`, `timer_duration_seconds`,
`context` (Not Set / Active / Not Active). `HeartRateVariabilityDataSampleRMSSD` ha `timestamp`,
`hrv_rmssd`. `RRIntervalSample` ha `rr_interval_ms`, `timestamp`, `hr_bpm`. Nessun file dello schema
relativo a heart/HRV/RR/ECG contiene "quality", "confidence", "accuracy", "reliab" o "artifact". Le
uniche occorrenze nello schema sono in Sleep, SleepLevel, GlucoseData e LabReportArtifactsResponse.

Questo dice cosa c'è **nello schema pubblico**, non come Terra tratta la qualità internamente né cosa
restituisce in pratica ogni provider.

## 7. Limiti

- Un solo dataset: dito, 22 adulti sani, attività di laboratorio, 491 finestre da 60 s. Non sono dati
  degli occhiali: l'app non salva il grezzo (patch proposta in `../patches/export-raw.patch`).
- L'SQI è un'**euristica non validata** con soglie tarate a mano sul prototipo nasale. Il termine di
  ampiezza non si trasferisce a un altro sito: qui è sempre saturo. Secondo il commento in `sqi.dart`,
  però, anche i PI misurati al naso (0,04–0,07%) sono sopra la soglia dello 0,02%. Probabilmente è
  saturo anche sugli occhiali, ma non è verificato.
- Il problema del punto fiduciale potrebbe essere diverso al naso (morfologia dell'onda diversa). Non verificato.
- Le soglie 0,96–0,98 sono post hoc.
- Nel formato WFDB il PPG è salvato a 12 bit con guadagno e offset, e lo si decima da 500 a 100 Hz.
  Rispetto allo stream reale degli occhiali mancano la perdita di pacchetti BLE e il possibile problema
  della doppia lettura del FIFO (`../docs/PIPELINE_ATTUALE.md` §1).
- L'RMSSD da PPG è calcolato per finestra, non sul buffer mobile di 60 intervalli dell'app.
- Il riferimento dipende dalle annotazioni R del dataset. Gli autori segnalano un ECG rumoroso durante
  il cammino.

## 8. Seconda analisi: fronte, vita reale (WildPPG)

Aggiunta dopo la restituzione degli occhiali, per avere un sito sulla testa.

**Dataset.** WildPPG (Meier, Demirel, Holz, NeurIPS 2024 D&B; dati **CC BY-NC-SA 4.0**, uso non
commerciale). PPG riflessivo alla fronte (MAX86141; verde 530, rosso 660, IR 950 nm), ECG Lead I allo
sterno, accelerometro, tutto a 128 Hz, circa 12 ore di vita reale per persona (escursioni, trasporti,
pasti, riposo).
- Il grezzo completo pesa 19,6 GB (16 file). Per restare sotto la soglia di ~3 GB ho scaricato solo i
  2 file più piccoli: partecipanti `an0` ed `e61`, 2,2 GB. Ho estratto i canali usati in
  `data/wildppg/*.npz` e cancellato il grezzo. `./download_wildppg.sh all` li scarica tutti.
- La versione su Hugging Face (632 MB) contiene finestre pre-elaborate e HR, **senza** l'ECG: non
  serve per l'HRV.

**Polarità (inferita, non dichiarata dagli autori).** WildPPG salva il PPG in polarità volume. Evidenze
in `results/wildppg_polarity.json`: l'onda media ha il massimo 336–367 ms (IR) e 273–320 ms (verde) dopo l'onda R; nel verde la
pendenza più ripida è la salita (rapporto pendenza +/− 1,74–1,81, contro 0,19–0,61 del grezzo
MAX30101 di PTT-PPG); il codice ufficiale passa `ppg_g.v` così com'è al toolbox *ppg-beats*, che si
aspetta la polarità volume. Per simulare l'app l'IR viene quindi **invertito** (run `app`); l'IR così
com'è corrisponde alla variante col picco sistolico (run `systolic`).

**Unità.** Il PPG è in frazione del fondo scala dell'ADC; viene moltiplicato per 4096 solo per dare un
senso alla soglia di presenza di 10 nA dell'SQI. Tutto il resto è indipendente dalla scala.

**Riferimento.** Picchi R rilevati con `ecg_rpeaks.py` (stile Pan–Tompkins, rifinitura sub-campione).
Validazione su PTT-PPG con l'ECG ricampionato a 128 Hz (`results/rpeak_validation.json`): sensibilità
e PPV mediane 1,0 (minimo 0,94), errore di temporizzazione mediano 1,6 ms. Con la pulizia RR (esclusi
gli RR a più del 20% dalla mediana di 11 intervalli), l'RMSSD di riferimento differisce da quello
manuale di 0,19 ms in mediana (90° percentile 0,66 ms). Su WildPPG sono escluse le finestre con più
del 10% di RR scartati: restano 1343 finestre su 1479.

**Risultati** (`results/wildppg_summary.json`; IC 95% con bootstrap a blocchi di 10 minuti dentro la
persona). RMSSD vero mediano **14,8 ms** (IQR 10,4–20,8).

| Condizione | Finestre tenute | Errore ass. mediano (IC 95%) |
|---|---|---|
| App (IR, polarità luce), nessun filtro | 67,2% | **136,1 ms** (128,5–144,0); bias +141,7; r = 0,12 |
| + SQI ≥ 0,4 per finestra | 39,2% | 130,3 ms; riduzione IC [−1,6; 10,5] |
| Finestre scartate da SQI ≥ 0,4 | 28,0% | 140,2 ms |
| + SQI ≥ 0,4 nel ciclo (come l'app) | 40,4% | 125,2 ms; riduzione IC [3,5; 15,6] |
| SQI ≥ 0,96 / 0,97 *(post hoc)* | 14,0% / 4,6% | 115,2 / 96,7 ms |
| Filtro accelerometro, stessa copertura | 14,0% / 4,6% | 137,4 / 114,2 ms |
| Stesso run ricampionato a 100 Hz | 66,3% | 134,7 ms |
| *Non nell'app*: IR col picco sistolico | 64,3% | 113,7 ms (103,7–121,3) |
| Verde, polarità luce | 89,4% | 109,0 ms |

Osservazioni:
- A differenza del dito, qui l'SQI **scatta**. La modulazione mediana è 2,45% (`an0`) e 4,46% (`e61`),
  quindi la penalità artefatti è attiva nel 56% e 68% dei secondi e l'SQI di finestra mediano è 0,47 e
  0,0. Scarta molte finestre ma non quelle sbagliate: 130 ms nelle tenute contro 140 ms nelle scartate,
  circa 9 volte l'RMSSD vero in entrambi i casi.
- Il **canale IR alla fronte porta poco battito** (`results/wildppg_channel_check.json`). Nel 20% di
  finestre più ferme, l'HR spettrale coincide con l'ECG (±5 bpm) nel 30,2% e 4,6% dei casi (IR) contro
  75,5% e 56,2% (verde). Anche il caso migliore per il rilevatore dell'app (verde, picco sistolico) dà
  69,0 e 62,8 ms su tutte le finestre e 62,5 e 54,1 ms su quelle ferme.
- Picchi rispetto all'onda R (run `app`): battiti persi 49,3% e 60,6%, IQR del ritardo 607 e 435 ms.

**Limiti specifici.** Solo 2 persone su 16: gli IC descrivono la variabilità dentro queste due persone,
non tra persone. La polarità è inferita. Il riferimento è automatico, anche se validato. Licenza non
commerciale.

## 9. Riprodurre

```bash
cd analysis
./reproduce.sh      # crea .venv se manca, scarica ~410 MB, test, analisi, figura, controllo Terra
```

Richiede Python 3 (usato 3.14.3), le versioni in `requirements.txt` e, per i test di equivalenza,
Dart (usato quello di Flutter). Seed: 20260928. Tempo: circa 1 minuto più il download.
`data/ptt_ppg/` (411 MB) si può cancellare e riscaricare.

SHA-256 dei risultati sul dito (identici su due esecuzioni complete):

```
f9585a79e486cd682141654a385de11b8aea14648cd63fd108cd33fa6c23719c  results/summary.json
64a32f45c3a7d369860b9ba5c393c8ddbffe4448c6a02dc78a19bb017c71b93e  results/sweep.csv
b02f17d2a137315de1a867f1d5551aa9d0e085c917525ad9b2f3bd9cb60a72b1  results/fiducial_check.json
```

SHA-256 dei risultati alla fronte (identici su due esecuzioni di `run_wildppg.py`):

```
c4587a81cc8eb61f0e466e8098253ed7f34eac42af6c6ac6e91f0eee8deccdda  results/wildppg_summary.json
89ec51b9b95b1fd6b6f865e78b8dc3a28d12188233d2210546d3e4e8d57d6eb6  results/wildppg_sweep.csv
f69e947435323ce9f2a771dac8357c567f452a66a79ea5fac09d681208773bc2  results/wildppg_windows.csv
```
