# Ladycat karaoke — stato al 27/08

Pipeline: lyrics.txt (con tag sezione) -> align2.py (wav2vec2 base, forced alignment per regioni) -> aligned.json -> render2.py (PIL -> ffmpeg ProRes 4444 alpha, a segmenti).

## Problemi noti
- Ball in ritardo: mediana +150 ms rispetto a Whisper, con derive fino a 1-2 s
  su Pre-Chorus 1 (44-50s) e Final Chorus (128-140s). Causa: modello speech
  (WAV2VEC2_ASR_BASE_960H) su cantato con phaser, senza separazione vocale.
  Qui MMS_FA (1.2 GB) andava OOM: sul Mac usare MMS_FA o whisperx, PRIMA demucs
  (htdemucs) per isolare la voce, poi allineare sulla traccia vocale.
- Chorus 1 ha 3 righe (Suno ha saltato l'ultimo "Two purrs"), gia' corretto in lyrics.txt.
- Buco 142-144s: possibile riga non cantata / ad-lib da verificare.
- Font: main 56px bold, parentesi 40px oblique (720p). Da uniformare se si vuole
  stessa grandezza e differenziare solo con corsivo/colore.
- Render 1080p: fare a segmenti (60 s) e concat con ffmpeg -c copy.

## Idea app
input mp3 + testo -> demucs -> forced alignment -> renderer parametrico -> mp4 / mov alpha
