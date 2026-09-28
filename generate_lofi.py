import math
import random
import struct
import wave

def generate_lofi_track(filename="lofi_track.wav", duration_sec=26.0, sample_rate=44100):
    num_samples = int(sample_rate * duration_sec)
    bpm = 84.0
    beat_duration = 60.0 / bpm
    eighth_duration = beat_duration / 2.0
    bar_duration = beat_duration * 4.0

    # Frequencies for chords (Cmaj7, Am7, Dm7, G7)
    # Cmaj7: C4 (261.63), E4 (329.63), G4 (392.00), B4 (493.88)
    # Am7:   A3 (220.00), C4 (261.63), E4 (329.63), G4 (392.00)
    # Dm7:   D4 (293.66), F4 (349.23), A4 (440.00), C5 (523.25)
    # G7:    G3 (196.00), B3 (246.94), D4 (293.66), F4 (349.23)
    chords = [
        [261.63, 329.63, 392.00, 493.88],
        [220.00, 261.63, 329.63, 392.00],
        [293.66, 349.23, 440.00, 523.25],
        [196.00, 246.94, 293.66, 349.23],
    ]

    audio_samples = [0.0] * num_samples

    # 1. Generate Chord Chords (Warm synth piano with slight low-pass feeling)
    for t_idx in range(num_samples):
        t = t_idx / sample_rate
        bar_num = int(t / bar_duration)
        chord = chords[bar_num % len(chords)]
        t_in_bar = t % bar_duration

        # Chord envelope: soft attack, gentle decay
        env = math.exp(-t_in_bar * 0.8) * 0.35

        chord_val = 0.0
        for freq in chord:
            # Main sine wave + subtle 2nd harmonic for warm rhodes vibe
            val = 0.7 * math.sin(2 * math.pi * freq * t) + 0.3 * math.sin(2 * math.pi * freq * 2 * t)
            chord_val += val
        
        audio_samples[t_idx] += chord_val * env * 0.15

    # 2. Add Drum Beat & Hi-Hats & Vinyl Crackle
    for t_idx in range(num_samples):
        t = t_idx / sample_rate
        beat_time = t % beat_duration
        eighth_time = t % eighth_duration

        # Kick drum on beat 1 and beat 3 (with kick syncopation)
        t_in_bar = t % bar_duration
        is_kick = (beat_time < 0.1) and (int(t / beat_duration) % 4 in [0, 2, 2.5])
        if is_kick:
            kick_env = math.exp(-beat_time * 25.0)
            kick_freq = 120.0 * math.exp(-beat_time * 30.0) + 45.0
            audio_samples[t_idx] += math.sin(2 * math.pi * kick_freq * t) * kick_env * 0.45

        # Snare drum on beat 2 and beat 4
        is_snare = (beat_time < 0.12) and (int(t / beat_duration) % 4 in [1, 3])
        if is_snare:
            snare_env = math.exp(-beat_time * 20.0)
            noise = (random.random() * 2.0 - 1.0)
            body = math.sin(2 * math.pi * 180.0 * t)
            audio_samples[t_idx] += (0.6 * noise + 0.4 * body) * snare_env * 0.25

        # Hi-hat on every 8th note
        if eighth_time < 0.04:
            hat_env = math.exp(-eighth_time * 80.0)
            noise = (random.random() * 2.0 - 1.0)
            audio_samples[t_idx] += noise * hat_env * 0.08

        # Subtle Vinyl Crackle
        if random.random() < 0.003:
            crackle = (random.random() * 2.0 - 1.0) * 0.04
            audio_samples[t_idx] += crackle

    # Normalize audio samples to [-1.0, 1.0] range
    max_val = max(abs(s) for s in audio_samples) or 1.0
    scale = 0.85 / max_val

    with wave.open(filename, "wb") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)

        packed_frames = bytearray()
        for s in audio_samples:
            sample_val = int(s * scale * 32767.0)
            sample_val = max(-32768, min(32767, sample_val))
            packed_frames.extend(struct.pack("<h", sample_val))
        
        wav_file.writeframes(packed_frames)

    print(f"Generated upbeat lo-fi track: {filename} ({duration_sec}s)")

if __name__ == "__main__":
    generate_lofi_track()
