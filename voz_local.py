"""Entrada de voz local via microfone + Faster Whisper (CPU).
A captura só acontece enquanto o usuário mantém o modo de escuta ativo.
"""
import threading

class VozLocal:
    def __init__(self):
        self.stream = None
        self.partes = []
        self.lock = threading.Lock()
        self._sd = None
        self._np = None
        self.gravando = False
        self._whisper = None

    def iniciar(self):
        if self.gravando:
            raise RuntimeError('O microfone já está ativo.')
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError as exc:
            raise RuntimeError('A voz ainda não está instalada. Execute Instalar voz.bat.') from exc
        self._sd, self._np = sd, np
        with self.lock:
            self.partes = []
        def callback(indata, frames, time_info, status):
            # Apenas copiar amostras; nunca faça inferência no callback do microfone.
            with self.lock:
                self.partes.append(indata[:, 0].copy())
        try:
            self.stream = sd.InputStream(
                channels=1, samplerate=16000, dtype='float32',
                blocksize=1600, callback=callback
            )
            self.stream.start()
            self.gravando = True
        except Exception as exc:
            if self.stream:
                try: self.stream.close()
                except Exception: pass
            self.stream = None
            raise RuntimeError(f'Microfone indisponível: {exc}') from exc

    def parar(self):
        if not self.gravando:
            raise RuntimeError('A gravação não estava ativa.')
        self.gravando = False
        self.stream.stop()
        self.stream.close()
        self.stream = None
        with self.lock:
            pedacos = self.partes
            self.partes = []
        if not pedacos:
            raise RuntimeError('O microfone não captou áudio.')
        audio = self._np.concatenate(pedacos).astype('float32')
        if len(audio) < 16000 * 0.5:
            raise RuntimeError('Gravação muito curta. Fale por pelo menos um segundo.')
        return audio

    def transcrever(self, audio):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError('Faster Whisper não instalado. Execute Instalar voz.bat.') from exc
        if self._whisper is None:
            # A primeira execução baixa automaticamente o modelo Whisper 'base'.
            self._whisper = WhisperModel('base', device='cpu', compute_type='int8')
        segmentos, info = self._whisper.transcribe(
            audio, language='pt', beam_size=3, vad_filter=True,
            condition_on_previous_text=False
        )
        return ' '.join(seg.text.strip() for seg in segmentos).strip()
