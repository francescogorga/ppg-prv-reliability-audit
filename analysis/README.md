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
| `oracle_check.py` | Prova 1: il limite massimo di un filtro qualsiasi (oracolo che conosce l'errore vero). |
| `calibrate_sqi.py` | Prova 2: soglie tarate su una parte delle persone e misurate sulle altre. |
| `tests/test_v2.py` | 3 test della v2 (battito sul picco sistolico). |
| `features.py`, `build_features.py` | Feature per minuto senza ECG (SQI e sue parti, battiti, somiglianza tra battiti, forma d'onda, accelerometro) e tabella con l'etichetta. |
| `quality_models.py` | Quale segnale riconosce meglio i minuti buoni: feature singole, regressione logistica, gradient boosting, oracolo (leave-one-subject-out). |
| `conformal.py` | Incertezza: intervalli con garanzia di copertura (conformal prediction). |
| `explain.py` | Explainability: SHAP sul modello dell'errore, coefficienti della logistica. |
| `robustness_quality.py`, `fig_tracking.py` | Controlli di robustezza (dentro attività e persona, circolarità, "i valori tenuti seguono la verità?") e figura del brief. |
| `tests/test_features.py` | 2 test delle feature su segnali sintetici. |
| `stress.py`, `dart_ref/stress_ref.dart`, `tests/test_stress.py` | Porting dell'indice di stress dell'app (`stress_detector.dart` + ciclo a 1 Hz di `home_page.dart`), verificato contro il Dart originale. |
| `build_stress.py`, `stress_eval.py`, `fig_brief.py` | Replay dello stress dell'app su dito e fronte; accordo con lo stress "da ECG", filtri, incertezza; figura del brief. |
| `reproduce.sh` | Rifà tutto da zero. |
| `results/` | Output (CSV, JSON, figura, log). |

## 2. Verifica del porting

`tests/test_port.py` confronta il porting con l'output delle classi Dart originali su 5 segnali
sintetici (100, 64 e 125 Hz; pulito, con artefatti di movimento, sensore staccato), sia con gate SQI
0,4 sia senza gate. Filtrato (tolleranza 1e-9), picchi (identici), SQI per campione (1e-12), RMSSD a
1 Hz, numero di intervalli nel buffer e buffer RR finale coincidono. Esito, con gli altri test: **39 passed**
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

## 9. Il filtro era sbagliato, o nessun filtro aiuta? (prove 1 e 2)

**v2 (non è nell'app).** È la stessa pipeline, con un'unica modifica: il rilevatore lavora sul segnale
filtrato cambiato di segno, quindi colloca il battito sul picco sistolico invece che sul piede
(`app_pipeline.py`, `PpgProcessor(systolic=True)`). La v1 resta identica all'app (test invariati); la
v2 ha 3 test propri. Risultati senza filtro: dito 18,1 ms (bias +43,8 ms, r = 0,06: pochi errori molto
grandi durante il movimento), fronte 113,7 ms. Sono uguali alla variante col segnale invertito usata prima.

**Prova 1 — oracolo** (`results/oracle_check.json`, `results/fig_oracle.png`). Ordino le finestre per
errore vero (serve l'ECG, quindi è irraggiungibile) e tengo le migliori: è il massimo che un filtro può
fare. Errore mediano tenendo il 50% delle finestre:

| | Oracolo | SQI app | Solo periodicità | Accelerometro | Senza filtro | Finestre buone (≤ 5 ms) |
|---|---|---|---|---|---|---|
| Dito, v1 (app) | 48,4 | 50,6 | 50,6 | 62,2 | 85,5 | 1,2% |
| Dito, v2 (picco sistolico) | 5,5 | 8,3 | 8,3 | 6,0 | 18,1 | 23,6% |
| Fronte, v1 (app) | 120,7 | 133,2 | 132,0 | 138,1 | 136,1 | 0% |
| Fronte, v2 (picco sistolico) | 96,5 | 109,0 | 109,6 | 109,9 | 113,7 | 0,1% |

- Sul dito l'SQI, **usato come classifica**, è quasi al livello dell'oracolo: il difetto era la soglia 0,4.
- Con la v1 nemmeno un filtro perfetto scende sotto ~48 ms tenendo metà dei dati, perché le finestre
  buone quasi non esistono. Alla fronte non esistono affatto.
- Sul dito il termine di ampiezza vale sempre 1, quindi SQI completo e sola periodicità danno la
  stessa classifica.

**Prova 2 — soglie tarate in modo onesto** (`results/sqi_calibration.json`).
- *Dito*: 200 divisioni casuali in 11 persone di taratura e 11 di test. La soglia è scelta sulla metà di
  taratura per tenere il 75/50/25% dei dati, poi applicata così com'è alla metà di test.
- *Fronte*: taratura su un partecipante, test sull'altro.
- *Trasferimento*: soglie tarate sul dito e applicate alla fronte.

Dito, v2, sulle persone di test (mediana [2,5°–97,5° percentile] sulle 200 divisioni; senza filtro 18,0 ms):

| Obiettivo | Filtro | Dati tenuti | Errore | Oracolo alla stessa copertura |
|---|---|---|---|---|
| 50% | SQI (= periodicità) | 50% [28–76] | **8,5 ms** [5,7–11,9] | 5,5 |
| 50% | Accelerometro | 50% [40–61] | **6,0 ms** [4,3–11,9] | 5,5 |
| 25% | SQI | 25% [10–45] | 7,6 ms [4,9–11,4] | 3,1 |
| 25% | Accelerometro | 24% [11–33] | 3,7 ms [2,3–5,4] | 2,7 |
| 75% | SQI | 74% [50–92] | 10,0 ms [7,7–16,5] | 9,1 |
| 75% | Accelerometro | 75% [63–88] | 11,9 ms [6,2–28,3] | 9,3 |

- **Con la v2 e una soglia tarata, il filtro funziona anche su persone mai viste**: tenendo metà dei
  dati l'errore si dimezza (da 18 a 8,5 ms con l'SQI, 6,0 con l'accelerometro). L'accelerometro è più
  vicino all'oracolo e la copertura che ottiene varia meno tra le divisioni; la soglia dell'SQI si
  trasferisce meno bene tra persone (coverage 28–76%).
- Con la v1 tarata: 50,7 ms al 50% (senza filtro 84,4), cioè ancora più di 2 volte il valore vero.
- *Fronte*: le soglie non si trasferiscono tra i due partecipanti. Tarate su `e61`, su `an0` non scartano
  nulla; tarate su `an0`, su `e61` tengono meno dati del previsto. Gli errori restano tra 80 e 146 ms.
- *Dal dito alla fronte*: le soglie del dito (0,95–0,985) tengono solo l'1–14% delle finestre della
  fronte, con errori di 39–75 ms. **Una soglia non si trasferisce tra siti.**

**Conclusione.** Il filtro dell'app era tarato male (soglia 0,4), ma non era il problema principale.
Prima va corretto il punto in cui si colloca il battito. Dopo, un filtro tarato su un riferimento
dimezza l'errore al prezzo di metà dei dati, e in laboratorio un semplice accelerometro fa almeno
altrettanto bene. Alla fronte, nella vita reale, nessun filtro basta con questi dati.

## 10. Quale segnale riconosce meglio i minuti buoni? ML, incertezza, explainability

Si parte dalla v2. Per ogni minuto si calcolano 24 feature **senza ECG** (`features.py`):
- l'SQI dell'app e le sue parti;
- statistiche sui battiti: trovati, scartati, stima dei persi, salti tra intervalli;
- somiglianza di ogni battito al battito medio (correlazione col template);
- forma d'onda: skewness, curtosi, purezza spettrale;
- accelerometro.

L'ECG serve solo per l'etichetta, cioè l'errore RMSSD del minuto; "buono" = errore ≤ 5 ms.
La fronte ora usa **tutti i 16 partecipanti** di WildPPG, scaricati e cancellati un file alla volta:
12.998 minuti, 10.945 con riferimento ECG affidabile. Con la v1 l'errore mediano è 106,1 ms, con la v2
89,2 ms (RMSSD vero mediano 21,3 ms); i minuti buoni con la v2 sono il 3,2%.

**Valutazione.** Leave-one-subject-out: il punteggio di ogni persona viene da un modello allenato
sulle altre. Per le feature singole anche la direzione (più alto = meglio o peggio) è scelta sulle
altre persone. Le metriche sono:
- **AURC**, la media dell'errore mediano sulla curva errore–dati tenuti (10–100%): più basso è meglio;
- **gap chiuso**, cioè quanto della distanza tra "nessun filtro" e oracolo viene recuperata;
- **AUROC** su "buono".

Gli IC sono calcolati con bootstrap per persona. Risultati in `results/quality_models.json` e
`results/fig_quality_models.png`.

| | Dito: AURC (gap chiuso) | Dito: errore al 50% | Dito: AUROC | Fronte: AURC (gap chiuso) | Fronte: errore al 25% | Fronte: AUROC |
|---|---|---|---|---|---|---|
| Nessun filtro | 18,1 | 18,1 | — | 89,2 | 89,2 | — |
| Oracolo (serve l'ECG) | 6,9 (100%) | 5,5 | — | 48,8 (100%) | 29,4 | — |
| Gradient boosting, tutte le feature | 7,1 (98%) | 5,5 | 0,96 | **49,6 (98%)** | 30,9 | 0,98 |
| Regressione logistica | 7,2 (97%) | 5,7 | 0,94 | 51,8 (92%) | 32,5 | 0,97 |
| Somiglianza tra battiti (da sola) | **7,0 (99%)** | 5,5 | 0,97 | 53,3 (89%) | 33,7 | 0,96 |
| Quota di battiti scartati | 7,4 (96%) | 5,6 | 0,90 | 53,4 (89%) | 34,9 | 0,95 |
| Accelerometro | 8,1 (89%) | 6,0 | 0,88 | 82,8 (16%) | 81,2 | 0,62 |
| **SQI dell'app** | 9,4 (78%) | 8,3 | 0,68 | 71,0 (45%) | 58,9 | **0,39** |

- Sul dito basta **una feature**, la somiglianza tra battiti, per arrivare quasi all'oracolo; il
  vantaggio sull'SQI è significativo (AURC, IC del miglioramento +1,2…+4,5 ms). I modelli di ML non
  aggiungono nulla.
- Alla fronte, nella vita reale, il **gradient boosting** è il migliore (98% del gap; miglioramento
  sull'SQI +10,0…+33,7 ms). L'SQI dell'app ha AUROC 0,39, peggio del caso. L'accelerometro, utile in
  laboratorio, qui non serve.
- **Trasferimento tra siti**: allenato solo sul dito e applicato alla fronte, il gradient boosting ha
  AURC 49,9 (contro 49,6 allenato sulla fronte); al contrario 7,1 (contro 7,1). Conta la
  **classifica**, non una soglia fissa, ed è per questo che si trasferisce.
- **Limite dei dati**: alla fronte anche l'oracolo, tenendo un quarto dei minuti, ha un errore
  mediano di 29 ms.
- **Bias di selezione**: sul dito i minuti tenuti al 50% hanno HRV vera più alta (25,8 contro 19,6 ms
  per la somiglianza tra battiti, 26,5 contro 19,1 anche per l'oracolo), perché sono quelli da seduti.
  Una HRV filtrata va interpretata sapendo che rappresenta di più il riposo. Alla fronte l'effetto è
  piccolo (20,7 contro 23,4 ms).

**Incertezza: conformal prediction** (`results/conformal.json`, `results/fig_conformal.png`). Per ogni
minuto si costruisce l'intervallo RMSSD ± q·σ(x), con σ(x) = errore previsto dal gradient boosting
+ 1 ms (intervallo *adattivo*), confrontato con un intervallo a larghezza fissa. Obiettivo: copertura
del 90%. Il modello è allenato su 2/3 delle altre persone e tarato sul restante terzo; la persona di
test non viene mai usata (20 ripetizioni).

| | Dito | Fronte |
|---|---|---|
| Copertura complessiva, adattivo / fisso | 89,4% / 88,0% | 89,3% / 89,3% |
| Larghezza mediana, adattivo / fisso | 58 / 263 ms | 223 / 341 ms |
| Persone con copertura < 80%, adattivo / fisso | 3 su 22 (min 45%) / 6 su 22 | 3 su 16 (min 63%) / 2 su 16 |
| Solo intervalli ≤ 20 ms: minuti tenuti, errore, copertura | 24,9%, 3,3 ms, 83% | 2,6%, 3,4 ms, 88% |
| Tarato sull'altro sito, adattivo / fisso | 89,1% / 96,2% | 89,5% / **68,1%** |

- La garanzia **in media** regge, anche cambiando sito, ma solo con l'intervallo adattivo: quello fisso,
  tarato sul dito e usato sulla fronte, scende al 68%.
- **Per singola persona** non è garantita: alcune restano sotto l'80%.
- Gli intervalli stretti coprono meno del 90%: garanzia marginale ≠ garanzia condizionale.
- Alla fronte gli intervalli sono onesti ma molto larghi (mediana 223 ms su un RMSSD di 21 ms):
  l'incertezza è reale, non un difetto del metodo.

**Explainability: SHAP** (`results/explain.json`, `results/fig_shap.png`). È il modello dell'errore
allenato su tutti i dati, solo a scopo di spiegazione.
- *Dito*: domina la somiglianza tra battiti (|SHAP| medio 0,66), poi la stima RMSSD stessa (0,25),
  l'energia dell'accelerometro a 1–5 Hz e i salti tra intervalli.
- *Fronte*: domina la stima RMSSD (0,43; più è alta, più il modello prevede errore, perché gli errori
  gonfiano l'RMSSD), poi il salto massimo tra intervalli (0,19) e la somiglianza tra battiti.
- *Importanza ≠ necessità*: senza la stima RMSSD il modello ottiene la stessa AURC (49,7 contro 49,6
  alla fronte, 7,1 contro 7,1 sul dito), perché l'informazione c'è anche nei salti tra intervalli. SHAP
  distribuisce il merito tra feature correlate.
- La logistica dà lo stesso quadro: sul dito i coefficienti più grandi sono la somiglianza tra battiti,
  alla fronte i salti tra intervalli e i battiti persi.

**Controlli di robustezza** (`robustness_quality.py` → `results/robustness_quality.json`; figura del
brief `results/fig_tracking.png`). Usano i punteggi leave-one-subject-out appena descritti.
- *Dentro l'attività (dito)*: la somiglianza tra battiti recupera il 98% del guadagno dell'oracolo anche
  dentro una sola attività (mediana su seduto, cammino e corsa); l'accelerometro solo il 28%. Il suo buon
  risultato complessivo veniva dal separare "seduto" da "in movimento".
- *Dentro la persona (fronte)*: gradient boosting 99%, somiglianza tra battiti 80%, SQI 59%, accelerometro 35%.
- *Circolarità*. L'etichetta è |RMSSD_ppg − RMSSD_ecg|; alla fronte, nel minuto mediano, il 79% della
  stima è errore (Spearman errore–stima 0,92). Un filtro senza modello che tiene i minuti con la stima più
  bassa recupera il 96% del guadagno dell'oracolo, quasi come il gradient boosting.
- *Criterio "i valori tenuti seguono la verità"* (Spearman tra RMSSD PPG ed ECG nei minuti tenuti, IC 95%
  con bootstrap per persona; si tiene il 50% sul dito e il 25% alla fronte):

| | Dito | Fronte |
|---|---|---|
| Nessun filtro | 0,08 (−0,17…0,34) | 0,20 (0,04…0,35) |
| Somiglianza tra battiti | **0,63** (0,15…0,90) | **0,50** (0,20…0,70) |
| Quota di battiti scartati | 0,47 | 0,52 (0,26…0,70) |
| Gradient boosting, tutte le feature | 0,70 (0,29…0,91) | 0,44 (0,19…0,65) |
| Gradient boosting senza feature derivate dagli RR | 0,61 | 0,43 |
| Tieni le stime più basse (nessun modello) | 0,52 (0,07…0,70) | **0,20** (0,03…0,38) |
| Accelerometro | 0,41 | 0,15 |
| SQI dell'app | 0,19 (−0,18…0,50) | 0,36 (0,16…0,50) |
| Oracolo | 0,82 | 0,70 |

- Differenza somiglianza tra battiti − "tieni le stime più basse": dito −0,03…0,32 (non significativa),
  fronte **0,10…0,42**. Differenza somiglianza tra battiti − SQI: dito **0,18…0,71**, fronte −0,07…0,35.
- PR-AUC per "buono" (≤ 5 ms), più onesta dell'AUROC quando i minuti buoni sono rari: dito somiglianza
  tra battiti 0,92, SQI 0,34; fronte gradient boosting 0,70, somiglianza tra battiti 0,67, SQI 0,05.
- **Conseguenza**: alla fronte la quasi perfezione del gradient boosting sulla curva dell'errore era in
  gran parte circolare. Col criterio "segue la verità" i segnali di coerenza dei battiti sono i migliori.
  Anche così, i valori tenuti restano circa 3 volte quelli veri (mediana PPG 65 ms contro ECG 22 ms).
  È stato SHAP (stima RMSSD come feature principale alla fronte) a suggerire questo controllo.

**Riproducibilità.** `quality_models.py`, `conformal.py`, `explain.py` e `robustness_quality.py` rieseguiti due volte: output
identici. `build_features.py` non contiene elementi casuali; non l'ho rieseguito due volte perché dura
circa 15 minuti.

## 11. L'errore sull'HRV arriva all'indice di stress? (la continuazione del caso d'uso del corso)

Lo scopo dell'app era un indice di stress da HR e HRV rispetto a una baseline personale. Qui si misura
quanto l'errore sull'HRV si trasmette a quell'indice.

- **Porting verificato.** `stress.py` riproduce `stress_detector.dart` e l'ordine del ciclo a 1 Hz
  (`update` solo se SQI ≥ 0,4, poi `compute`). Su tre sequenze sintetiche punteggio e livello
  coincidono secondo per secondo con il Dart originale (`tests/test_stress.py`).
- **Replay** (`build_stress.py`). Per ogni secondo si confrontano quattro versioni:
  - **ECG**: HR (mediana degli ultimi 10 RR) e RMSSD (ultimi 60 RR consecutivi puliti) dall'ECG. È
    quello che l'app mostrerebbe con battiti perfetti: il riferimento. Non è una misura indipendente
    di stress;
  - **app com'è** (v1, filtro SQI nel ciclo);
  - **v2**;
  - **v2 con il filtro SQI dell'app**.

  La baseline di 60 s parte a inizio sessione: una sessione per registrazione sul dito, sessioni da
  30 minuti sulla fronte. Si valutano i minuti dopo la baseline con riferimento ECG affidabile: 424 sul
  dito, 10.208 sulla fronte.
- **Valutazione** (`stress_eval.py` → `results/stress_eval.json`, `results/stress_eval_stdout.txt`).
  - *Metriche*: accordo e kappa di Cohen tra livelli; falsi allarmi = minuti calmi da ECG in cui l'app
    mostra "agitato" o "stressato"; persi = il contrario.
  - *Filtri di visualizzazione*: soglia scelta sulle altre persone (leave-one-subject-out) per mostrare
    il 50% o il 25% dei minuti; se il minuto di baseline non passa la soglia, la sessione non viene
    mostrata.

| | Minuti mostrati | Kappa (IC 95%) | Falsi allarmi | Persi |
|---|---|---|---|---|
| Dito — app com'è | 100% | 0,28 (0,21–0,36) | 31% | 26% |
| Dito — v2 | 100% | 0,40 (0,29–0,52) | 25% | 22% |
| Dito — v2 + coerenza battiti, 50% | 46% | 0,68 (0,52–0,79) | 13% | 8% |
| Dito — v2 + coerenza battiti, 25% | 19% | 0,79 (0,55–1,00) | 13% | 0% |
| Dito — v2 + "stime più basse", 25% | 21% | 0,61 (0,34–0,89) | 9% | 23% |
| Fronte — app com'è | 91% | 0,15 (0,12–0,19) | 43% | 35% |
| Fronte — v2 | 100% | 0,13 (0,08–0,19) | 51% | 31% |
| Fronte — v2 + coerenza battiti, 25% | 16% | 0,33 (0,16–0,42) | 36% | 17% |

- Sul dito la coerenza dei battiti non migliora l'accordo tenendo solo i minuti facili: tra quelli
  tenuti al 50% i calmi sono il 70%, contro il 72% del totale. Il filtro "stime più basse" al 25% invece
  scarta proprio gli episodi di stress (1 minuto "stressato" su 89 tenuti) e ne perde il 23%. Sulla
  kappa i due filtri non sono distinguibili (IC sovrapposti).
- **Incertezza** (conformal sul punteggio, 90%, persona di test mai usata). Copertura 90,4% sul dito e
  90,0% sulla fronte; larghezza mediana 49 punti sul dito e 100 (tutta la scala) sulla fronte. Il
  livello è "sicuro" (intervallo dentro una fascia) nel 34% e nel 24% dei minuti, ma è quasi sempre
  "calmo" (98% e 99,6%). Alla fronte l'accordo dei livelli sicuri (83%) è uguale a quello di chi
  risponde sempre "calmo" (82,8%), con kappa 0,03 e il 98% degli episodi persi. Gli intervalli sono
  onesti ma non permettono di confermare lo stress.

## 12. Riprodurre

```bash
cd analysis
./reproduce.sh      # crea .venv se manca, scarica ~410 MB, test, analisi, figura, controllo Terra
```

Richiede Python 3 (usato 3.14.3), le versioni in `requirements.txt` e, per i test di equivalenza,
Dart (usato quello di Flutter). Seed: 20260928. Tempo: circa 1 minuto più il download.
`data/ptt_ppg/` (411 MB) si può cancellare e riscaricare.

SHA-256 dei risultati sul dito prima dell'aggiunta della v2 (identici su due esecuzioni complete; le versioni attuali sono in fondo):

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

Versioni attuali, dopo l'aggiunta della v2 e delle prove 1–2 (i valori della v1 sono invariati,
verificato chiave per chiave; identici su due esecuzioni):

```
3e08eeb89edcef759ed3f4787a7f9dd280a2fe75bd2e8acd2da08e3264fcac69  results/summary.json
e07742d15e1f3d39fc6a653b0ffd1a411807a7ba03874fb1a59d8ecbf7e54a00  results/sweep.csv
d7ee80ad8c4828990ee720aa8c01ade15ad91b35f876ab87be44b472424ea76e  results/wildppg_summary.json
c7c36aabfd3b416dd4f65ad3fb3b4aefb6dc12fd26cba42f3caf487c99cee6a9  results/wildppg_sweep.csv
0788494a683c284bcae563b84773e14e17f0be741ef30a23912506ca3d0cfa31  results/oracle_check.json
bfb3d2b6af0198315bffa69950bdaa828f4ff7f7f29e63cf6491d7c3a1ac77a3  results/sqi_calibration.json
```

Sezione 10 (identici su due esecuzioni; le tabelle delle feature sono le versioni usate):

```
b5ff68ae0feeab04f437d44e72823184f9a79b7b00b42c98871197c4154f956e  results/quality_models.json
8bec761f335418e0ff184ee7c9f1b69472dca30fd77f8e3089378612298c6356  results/robustness_quality.json
20b19b2cf75dea517e9266be47f1d370e1e791b100ac57f2480be9275dbfb7c5  results/conformal.json
3ab751d8133b598d209db93651c5b3034d05f0c389c024ab67f805de3e1363a5  results/explain.json
```

Sezione 11 (stress; `stress_eval.json` identico su due esecuzioni, le altre tabelle sono deterministiche):

```
4aac5823108b2a18f0d70d2c3f7217753595a4e2a3570e636d0b175df937336e  results/stress_finger.csv
72ab83355ad7cd3affbec9dbb66c2135791e270ab6d10623058563fd0ca20524  results/stress_forehead.csv
690aef26171442739d51a35449ec10acd072e55176945a03bfa94f49cf7bdaf6  results/stress_eval.json
```
