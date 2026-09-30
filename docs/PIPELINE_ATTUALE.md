# Pipeline attuale (stato del codice al 2026-09-28)

Descrive cosa fa **oggi** il codice, non cosa era previsto. Tutti i percorsi sono relativi a
`smart_wearables_app_stress/lib/` salvo indicazione diversa. Riferimenti nel formato `file:riga`.

Il porting Python riga per riga di questa pipeline è in `analysis/app_pipeline.py`. È verificato
contro le classi Dart originali (eseguite senza modifiche da `analysis/dart_ref/ref.dart`):
filtrato, picchi, SQI, RMSSD e buffer RR coincidono nei test sintetici. Per la suite attuale
e i risultati della review, vedere `docs/FINAL_REVIEW.md`.

Nota terminologica: la variabilità degli intervalli PPG è PRV, anche se l’app la chiama HRV.
I percorsi al firmware, all’app e alla patch qui citati appartengono al progetto originale,
non distribuito in questa repo. Questo documento ne conserva la descrizione storica.

---

## 0. Architettura in una riga

Il firmware (`PPG_Temp/`) campiona e spedisce **grezzo** a 100 Hz. **Tutta** l'elaborazione
(filtro, picchi, HR, HRV, SQI, SpO₂/PI, stress) gira nell'app Flutter sul telefono.
Il firmware non calcola nessuna metrica (vedi `docs/FATTI_CV.md`).

```
MAX30101 (IR, Red) + MAX30205 (temp)
   │  firmware PPG_Temp, TIM2 @ 100 Hz: legge FIFO, temp 1 Hz, invia frame BLE da 20 byte, scrive NAND
   ▼
connection_page.dart:227-265   buffer + risincronizzazione dei frame '{' … '}'
   ▼
home_page.dart:151-199  _onPacket (per ogni frame, 100 Hz)
   ├─ decode → IR/Red in nA, temperatura in °C
   ├─ PpgProcessor.process(IR, goodQuality: SQI ≥ 0.4)   media 2 campioni → band-pass → picchi → RR
   ├─ dopo 300 frame (3 s): SQI.push / SQI.updateIntervals / PpgMetrics.push
   ▼
home_page.dart:212-280  _tickSecond (1 Hz)
   ├─ RMSSD sul buffer RR
   ├─ StressDetector.update(...) solo se SQI (tick precedente) ≥ 0.4
   ├─ StressDetector.compute() → score 0-100 + livello
   └─ UI + serie per storico/CSV
```

---

## 1. Firmware (solo lettura, per contesto) — `PPG_Temp/Core/Src/main.c`

| Cosa | Dove | Valore |
|---|---|---|
| Timer di acquisizione | `main.c:622-626`, `PPG_Temp/MainBoard_IMU_Logger.ioc:277,373-374` | TIM2 prescaler 7200, period 100 su clock 72 MHz → **100 Hz** |
| Configurazione MAX30101 | `main.c:221-227` | modalità SpO₂, FIFO senza media (`sample_avg=0`), `SpO2Config(0x01,0x01,0x03)` = range ADC 4096 nA, 100 campioni/s, impulso 411 µs (18 bit), correnti LED 0x4B |
| Callback di acquisizione | `main.c:881-921` | legge PPG, temperatura ogni 100 cicli (1 Hz), `BLE_SendPacket`, timestamp, scrittura NAND |
| Elaborazione del segnale | — | **nessuna** (nessun filtro, picco o HR nel firmware) |

Possibile problema, non verificabile (hardware restituito): in `main.c:886-887` il FIFO viene letto
**due volte** per tick (`MAX30101_ReadSample` legge 6 byte, poi `MAX30101_ReadFIFO` ne legge altri 6, ed
è il secondo campione a essere inviato). Controllo sul datasheet (`MAX30101EFD.pdf`, pag. 14-17):
ogni lettura di un campione fa avanzare il puntatore di lettura. La procedura raccomandata è leggere
prima `FIFO_WR_PTR` e leggere al massimo `FIFO_WR_PTR − FIFO_RD_PTR` campioni; il firmware non lo fa.
Il sensore produce circa 1 campione per tick (100 campioni/s, clock interno indipendente da quello
dell'MCU) e il firmware ne legge 2, quindi almeno una delle due letture trova normalmente il FIFO vuoto.
Il datasheet **non specifica** cosa restituisce una lettura oltre i campioni disponibili: il contenuto
del campione inviato (nuovo, ripetuto o vecchio) non si può stabilire senza l'hardware. Inoltre `raw_ppg` è inviato senza la
maschera a 18 bit applicata in `ppg_driver.c:236,241`, e l'app non la applica (`home_page.dart:162-163`).

## 2. Decoder del frame BLE (20 byte)

Ricezione e risincronizzazione: `connection/connection_page.dart:227-265`. Accumula i byte delle
notify, cerca `{` (123), accetta il blocco se il byte 19 è `}` (125), altrimenti scarta un byte e
riprova.

Decodifica: `home_page.dart:151-177`.

| Byte | Contenuto | Decodifica nell'app |
|---|---|---|
| 0 | `{` 0x7B | controllato (`home_page.dart:153`) |
| 1-2 | contatore campioni uint16 BE | **non usato** dall'app |
| 3-5 | Red, 24 bit BE | `raw × 0.015625` → nA (`home_page.dart:16,162,164`) |
| 6-8 | IR, 24 bit BE | `raw × 0.015625` → nA (`home_page.dart:163,165`) |
| 9-10 | temperatura int16 BE | `raw × 1/256` °C; errore se `-32768` o fuori da [-40, 60] °C (`home_page.dart:167-177`) |
| 11-18 | padding | ignorato |
| 19 | `}` 0x7D | controllato |

`0.015625 nA/LSB` corrisponde a range ADC 4096 nA / 2¹⁸, coerente con la configurazione del firmware.
La frequenza di campionamento è fissata nell'app a 100 Hz (`home_page.dart:18`) e passata come
parametro `fs` a tutte le classi di `processing/`.

## 3. Ordine delle operazioni per ogni frame — `home_page.dart:151-199`

1. `_ppg.process(irNa, goodQuality: _sqi.value >= 0.4)` (`:183`). L'SQI usato è quello **prima** di
   inserire il frame corrente.
2. La forma d'onda filtrata va sempre al grafico (`:186`).
3. Solo dopo i primi 300 frame (3 s) (`:189-198`): `_sqi.push(filtered, raw IR)`,
   `_sqi.updateIntervals(buffer RR)`, `_metrics.push(red, ir)`.

## 4. `processing/ppg_processor.dart`

Opera sul **solo canale IR**.

| Stadio | Dove | Dettaglio attuale |
|---|---|---|
| Media mobile | `:209-231` | media di 2 campioni sul grezzo; il primo campione non viene elaborato |
| Passa-alto | `:39-49`, `:217` | biquad Butterworth 2° ordine, **0,5 Hz**, trasformata bilineare con prewarping, Q = 1/√2 |
| Passa-basso | `:51-61`, `:217` | biquad Butterworth 2° ordine, **3,5 Hz** |
| Rilevamento picchi | `:71-130`, `:218-223` | massimo locale (`x[n-1] > x[n-2]` e `x[n-1] > x[n]`); soglia `media + 0,8·σ` su finestra mobile di **4 s**; refrattario **400 ms** (max ≈ 150 bpm); attivo quando la finestra è piena a metà |
| Accettazione RR | `:141-169` | un intervallo tra due picchi è accettato solo se `goodQuality` **e** 300 < RR < 1500 ms (40-200 bpm) **e**, dopo i primi 3, entro ±30% della mediana degli ultimi ≤8 accettati |
| Buffer RR | `:139,149` | ultimi **60** intervalli accettati |
| HR | `:171-192` | `60000 / mediana` degli ultimi ≤10 intervalli; `null` se < 3 |

Il coefficiente del filtro coincide con `scipy.signal.butter(2, fc, fs=fs)` (test in `analysis/tests/test_port.py`).

Nota sulla polarità: il rilevatore cerca i **massimi** del segnale IR così come arriva dal MAX30101,
senza inversione. Nel grezzo di un PPG a riflessione la luce ricevuta **diminuisce** in sistole, quindi
i massimi del grezzo cadono vicino al piede dell'onda (fine diastole), non al picco sistolico.
L'effetto sull'HRV viene misurato in `analysis/` (vedi `analysis/README.md`).

## 5. `processing/sqi.dart` — Signal Quality Index

Finestra di **5 s** (`:16-17`) su due buffer: filtrato (`lastFiltered`) e grezzo IR in nA.

Valore (`:34-64`), in ordine:

1. meno di 2,5 s di dati → **0**
2. `DC = media(grezzo)`; se `DC < 10 nA` → **0** (sensore non a contatto, `:14,38`)
3. picco-picco del grezzo < 0,001 → **0**
4. `indice di modulazione = picco-picco(filtrato) / DC`
5. `punteggio ampiezza = clip(modulazione / 0,0002, 0, 1)` (score pieno allo 0,02%, `:13`)
6. se `punteggio ampiezza < 0,1` → **0** (`:48`)
7. `periodicità = clip(1 − 0,5·CV)` con CV = σ/μ degli intervalli RR nel buffer (≤60); 0 se < 3 intervalli (`:66-84`)
8. **penalità artefatti**: 0 se modulazione > 3%, 0,5 se > 2%, altrimenti 1 (`:52-59`)
9. `SQI = (0,40·ampiezza + 0,60·periodicità) × penalità`, limitato a [0, 1] (`:62`)

I commenti nel codice (`:10-13`) dicono che la soglia di ampiezza è stata abbassata allo 0,02% in base
a valori di PI misurati sul prototipo nasale (0,04% e 0,07%). Nel repository non ci sono dati
salvati di quelle misure.

Proprietà che derivano dalla formula (verificate in `analysis/tests/test_port.py`):

- Finché non ci sono almeno 3 intervalli nel buffer, la periodicità vale 0 e quindi **SQI ≤ 0,40**.
- Gli intervalli entrano nel buffer solo se SQI ≥ 0,4 (§3). L'avvio funziona solo se il punteggio
  di ampiezza è saturo (1,0) e la penalità è 1; basta una modulazione sotto lo 0,02% perché il
  buffer resti vuoto.
- Con una soglia > 0,4 al posto di 0,4 il buffer resterebbe **sempre** vuoto (test `test_gate_above_04_can_never_bootstrap`).

Usi dell'SQI nell'app:

| Uso | Dove |
|---|---|
| Accettazione di ogni RR (`goodQuality`) | `home_page.dart:183` |
| Aggiornamento dello stress detector solo se SQI ≥ 0,4 | `home_page.dart:224-233` |
| HR mostrata solo se SQI ≥ 0,4 | `home_page.dart:238` |
| Dialog "Poor Signal Quality" se SQI < 0,4 | `home_page.dart:272-306` |
| Card SQI: ≥ 0,7 / ≥ 0,4 / < 0,4 | `home_page.dart:598-615` |

## 6. HRV — `processing/stress_detector.dart:203-214`, chiamata in `home_page.dart:213`

`RMSSD = √(media((RR[i] − RR[i−1])²))` calcolato **ogni secondo** su tutto il buffer RR (fino a 60
intervalli accettati, circa l'ultimo minuto). Se un battito è stato scartato, gli intervalli
adiacenti nel buffer non sono consecutivi nel tempo, ma la differenza viene calcolata lo stesso.

## 7. `processing/ppg_metrics.dart` — SpO₂ e Perfusion Index

Finestra di 4 s su Red e IR **grezzi** (`:10-21`).
`PI = picco-picco(IR)/media(IR) × 100` (`:35`). `SpO₂ = 110 − 25·R`, `R = (AC/DC)_red / (AC/DC)_ir`,
`null` fuori da [70, 100] (`:37-43`). Il PI entra nella baseline dello stress detector ma **non** nello
score. SpO₂ e PI sono mostrati nel footer di debug (`home_page.dart:386-391`), la SpO₂ va nello storico.

## 8. `processing/stress_detector.dart` — indice di stress

Istanza: `baselineSeconds: 60, updateRateHz: 1, slowWindowSeconds: 12` (`home_page.dart:49-53`).

- **Baseline manuale**: parte con il pulsante "Start Baseline Calibration" (`home_page.dart:370-372,576-579`),
  raccoglie 60 aggiornamenti accettati (può durare più di 60 s con il gate SQI) e salva media e deviazione standard di HR e RMSSD (`:143-193`). Il parametro
  `startBaseline` di `HomePage` (`home_page.dart:23,27`) non è usato.
- **Valori correnti**: media degli ultimi 12 valori validi accettati (`:92-95,221-222`), non necessariamente 12 s di calendario.
- **Score** (`:216-260`): per HR `z = (HR − HR_base)/max(SD_base, 2 bpm)`, per RMSSD
  `z = (RMSSD_base − RMSSD)/max(SD_base, 5 ms)`. Ogni z è mappato linearmente in [0,1] (0 alla
  baseline, 1 a z ≥ 2,5, `:290-295`). Pesi 0,5 + 0,5, rinormalizzati se manca un termine.
  Score = media pesata × 100, poi media esponenziale con α = 0,35 (`:255`).
- **Livelli con isteresi** (`:264-287`): Aroused entra a 35 ed esce sotto 25; Stressed entra a 65 ed esce sotto 55.
- **Temperatura e PI**: raccolti nella baseline ma **non usati** nello score (commento `:97-98`).

## 9. Storico ed export — `history/`

Ogni secondo l'app salva HR, HRV, SpO₂, temperatura e stress (`home_page.dart:250-268`). L'export
CSV (`history/history_page.dart:49-133`) ha le colonne
`Session_Start_Time,Timestamp,HR_bpm,HRV_RMSSD_ms,SpO2_percent,Temp_C,Stress_Score`.
**Non** esporta né il segnale grezzo né l'SQI: per questo i dati del prototipo non si possono
rianalizzare offline. Una patch per aggiungerli è proposta in `patches/export-raw.patch` (non applicata).

## 10. Modalità demo

`demo/demo_stream.dart` genera frame sintetici byte-identici a quelli del firmware (100 Hz, seed 42),
ma il punto d'ingresso nella UI è commentato (`connection/connection_page.dart:350-362`).
