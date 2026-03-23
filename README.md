# RGB Matrix Music Visualizer



A real-time music visualizer running on a Raspberry Pi with a 64×64 HUB75 RGB LED matrix. Captures audio from a microphone, runs a Fast Fourier Transform to extract frequency data, and maps it to a rainbow spectrum of animated bars on the matrix.

![IMG_2440 (2)](https://github.com/user-attachments/assets/128d9e71-3bbd-48f5-bd45-21626a84ecaa)

---

## How it works

### 1. Capture audio
Raw audio is recorded from a microphone using `pyaudio` at 44,100 samples per second. Each frame grabs 2048 samples and converts them from raw bytes into float32 numbers ready for math.

```python
samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
```

### 2. Run the FFT
A Fast Fourier Transform converts the time-domain samples into frequency-domain data. `rfft` returns 513 complex numbers — one per frequency bin from 0 Hz to 22,050 Hz. Taking `np.abs()` collapses each complex number into a plain loudness value.

```python
fft       = np.fft.rfft(samples)
magnitude = np.abs(fft)
```

Each bin's frequency is implicit — determined by its position:
```
frequency = index × (SAMPLE_RATE / CHUNK) = 21.5 Hz per bin
```

### 3. Split into frequency buckets
The magnitude array is split into `NUM_BARS` buckets using **logarithmic spacing** from 200 Hz to 16,000 Hz. Log spacing is better than linear because each bar covers one musical octave rather than an equal Hz slice — matching how human ears perceive pitch.

```
Linear (bad):  bar 0 = 200–1200 Hz  (3 octaves crammed into one bar)
Log    (good): bar 0 = 200–290 Hz   (one octave per bar)
```

`np.max()` picks the loudest bin in each bucket — if any frequency in that range is active, the bar reacts.

### 4. Normalize and boost
Each bar is divided by `FFT_SCALE` to bring values into the 0.0–1.0 range. A progressive boost multiplier compensates for the natural physics of sound where high frequencies always carry less energy than bass.

```
bar 0  → 1.0x boost  (bass, already loud)
bar 8  → 2.0x boost
bar 15 → 3.0x boost  (treble, needs help)
```

### 5. Draw to the matrix
Each bar maps to a column of pixels. Height = bar value × 62 pixels × GAIN. Color is determined by position using HSV color space, creating a rainbow effect from left to right. The canvas is swapped on VSync to prevent flickering.

```
bar 0  (bass)   → red
bar 8  (mid)    → cyan
bar 15 (treble) → purple
```

---

## Hardware

| Component | Details |
|---|---|
| Raspberry Pi | 3B+ or 4 recommended |
| RGB LED Matrix | HUB75 64×64 panel |
| Microphone | USB mic or I²S mic (INMP441) |
| RGB Matrix HAT | Adafruit RGB Matrix Bonnet |

---

## Installation

### Dependencies
```bash
sudo apt install python3-pyaudio portaudio19-dev
pip3 install numpy
```

### RGB Matrix library
Follow the [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) installation guide for the `rgbmatrix` Python binding.

---

## Usage

```bash
sudo python3 visualizer.py
```

Press `Q` or `Escape` to quit cleanly.

---

## Configuration

All tuning knobs are at the top of `visualizer.py`:

| Variable | Default | Effect |
|---|---|---|
| `CHUNK` | `2048` | Samples per frame — higher = more frequency detail, more latency |
| `NUM_BARS` | `16` | Number of frequency bars — up to 64 for one pixel per bar |
| `SMOOTHING` | `0.6` | How fast bars fall — lower = snappier, higher = floatier |
| `GAIN` | `2.0` | Bar height multiplier — increase if bars are too short |
| `FFT_SCALE` | `600000.0` | Max expected FFT value — increase if bars always max out |

---

## Debugging

Logs are written to `debug.log`. Watch them live in a second terminal:

```bash
tail -f debug.log
```

---

## Project structure

```
visualizer.py       # main script
debug.log           # runtime logs (generated on run)
README.md
```
