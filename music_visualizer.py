import curses # Library for reading keyboard input (q or escape for quit)
import numpy as np # Math library that handles the FFT and array operations
import pyaudio # Handles microphone
from rgbmatrix import RGBMatrix, RGBMatrixOptions # Matrix library
import logging # For debugging purposes
# Call tail -f debug.log on a seperate terminal to see logs
logging.basicConfig(filename="debug.log", level=logging.DEBUG, format="%(message)s")

CHUNK = 2048 # Audio samples per frame, the greater samples, the better frequency details
SAMPLE_RATE = 44100 # 44100 snapshots every second (think of it as a flip book, the more the smoother), chose this value to be at the edge of human hearing
NUM_BARS = 32 # X frequency bars across 64px matrix, 64/X px wide each
SMOOTHING = 0.6 # How fast bars fall. Lower = snappier, Higher = floatier
GAIN = 2.0 # Multiplier of how bars grow (increase if bars move too little)
FFT_SCALE = 600000.0 # Max FFT value for loud audio. Divide by this converts FFT to 0.0-1.0 range. If bar maxes, raise num, otherewise lower it.

# Finds a microphone connected to the pi
def find_input_audio(pa):
	for i in range(pa.get_device_count()):
		info = pa.get_device_info_by_index(i)
		# If we find an audio device, return its index
		if info["maxInputChannels"] > 0:
			logging.debug(f"Using audio device {i}: {info['name']}")
			return i
	logging.debug("WARNING: no audio device found")
	return None

# Process the audio we take in from input device
def get_bars(raw, num_bars):
	# Converts raw mic bytes to array of numbers
	# raw = bytes, np.int16=16-bit integer (-32,768 to +32,767), .astype converts this into decimal for FFT
	samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
	# Run FFT (Fast Fourier Transform) and takes the magnitude
	# samples (time domain) => input array
	# Function computes 1-d n-point DFT of a real valued array through FFT
	# Returns an array of 513 complex numbers, called frequency domain
	# Complex number tells us how loud frequency is (magnitude), and what cycle frequency is (phase) => we only care about magnitude
	fft = np.fft.rfft(samples)
	magnitude = np.abs(fft) # 513 plain positive numbers (loudness only)
	
	# Next, we are going to throw away frequencies we don't care about (200 Hz- 16000 Hz)
	# Only way to do this is to figure out which index positions correspond to the frequencies, then slice the array
	# SAMPLE_RATE / 2 is the Nyquist limit (to accurately detect frequency, you need to sample at least twice as fast as that frequency)
	edges = np.logspace(np.log10(200), np.log10(16000), num_bars + 1)
	
	# We take the logspace here instead of linspace because doubling frequency = one octave
	# Problem with linear division is that it adds the same Hz to each bar, so 3 octaves are in bar 0
	# Log division means one bar = one octave
	edges = (edges / (SAMPLE_RATE / 2) * len(magnitude)).astype(int)
	
	# Saftey check to make sure no edges are below index 1 or above valid index
	edges = np.clip(edges, 1, len(magnitude) - 1)
	
	# Now for each bar, we want the loudest bin between 2 edges
	bars = []
	for i in range(num_bars):
		low = edges[i]
		high = edges[i + 1]
		if low >= high:
			bars.append(0.0) # Saftey check
		else:
			bars.append(float(np.max(magnitude[low:high]))) # Get the loudest number between 2 edges	
	# Now each bin is a number (loudness) at positon (frequency)
	
	# Divide each bar by FFT_SCALE to normalize to 0.0-1.0
	# Min is used so it cant go above 100% height
	normalized_bars = [min(b / FFT_SCALE, 1.0) for b in bars]
	
	# Boost higher frequency bars to compensate (low frequencies cary more energy than high ones)
	# This is to make higher frequency bars more noticable
	for i in range(num_bars):
		boost = 1.0 + (i / (num_bars - 1)) * 2.0 # Unique multiplier based on index i
		normalized_bars[i] = min(normalized_bars[i] * boost, 1.0) # Min is 1.0 to prevent errors
	
	# This is purely for debugging purposes to see percentage of each bar
	for i in range(num_bars):
		logging.debug(f"bars {i} : height percentage {normalized_bars[i] * 100}%")
	
	return normalized_bars
	
	# To summarize:
	# 1. We convert raw mic bytes -> int16 numbers -> float32 decimals (frombuffer + astype)
	#    Run rfft to get complex numbers, then we get the magnitude using np.abs() for real values
	# 2. Create NUM_BARS + 1 edges from 200 Hz to 16000 Hz using logspace
	#    Logspace is better than linear space because it results in one bar having one musical octave
	#    Linearspace would cram 3 octaves into one bar
	#    Starting at 200 Hz and ending at 16000 Hz filters out unwanted frequencies
	# 3. Then we split the magnitude into NUM_BARS buckets, np.max() picks loudest bin per bucket
	#    Bucket 0 = lower frequency, Bucket NUM_BARS - 1 = highest frequency
	# 4. Normalize each bar using FFT_SCALE so its in range of 0.0 - 1.0
	# 5. Apply boost multiplier to increase bar index with highest frequencies
	#    This is to compensate for high frequencies naturally carrying less energy than low ones
	# 6. Finally, we have our NUM_BARS values which are the final bar heights on the RGB matrix board display

# Paint the RGB Matrix
def draw(canvas, bars):
	canvas.Clear() # Clear canvas
	num_bars = len(bars) # Gets how many bars there are regardless of how many are passed in
	
	# Special case, if we have 64 or more bars, each bar is exactly 1 pixel wide
	if num_bars >= 64:
		for i, h in enumerate(bars): # Loops through i index and h height value
			bar_height = min(int(h * 62 * GAIN), 62) # Converts to pixel height, caps at 62 pixels
			
			if bar_height == 0: # Do nothing if height is 0
				continue
			
			hue = i / num_bars # 0.0 (red), 0.5 (cyan), 0.94 (purple) -> creates rainbow effect
			r, g, b = hsv(hue) # converts hue to RGB values
			
			for row in range(bar_height):
				# i is the x coordinate, one pixel columnn per bar
				# 63 - row converts to top-down pixel coords. Row 0 = pixel 63
				canvas.SetPixel(i, 63 - row, r, g, b)
			
		return # Skip code below if special case

	# Now we deal with fewer than 64 bars
	bar_width = max(1, (64 // num_bars) - 1) # Divide evenly for width per bar, -1 to leave gap
	gap = 1
	step = bar_width + gap # Total space each bar occupies including gap
	
	for i, h in enumerate(bars):
		bar_height = min(int(h * 62 * GAIN), 62)
		if bar_height == 0:
			continue
		hue = i / num_bars
		r, g, b = hsv(hue)
		
		x = i * step # Left edge pixel of bar
		
		# Now we are looping through, filling pixels of the rectangular bar
		for row in range(bar_height):
			y = 63 - row
			for col in range(bar_width):
				canvas.SetPixel(x + col, y, r, g, b)

# Converts hue value (0.0 - 1.0) to RGB values
# Built for rainbow effect
def hsv(h):
    i = int(h * 6)
    f = h * 6 - i
    i %= 6
    if i == 0: return 255, int(f*255), 0
    if i == 1: return int((1-f)*255), 255, 0
    if i == 2: return 0, 255, int(f*255)
    if i == 3: return 0, int((1-f)*255), 255
    if i == 4: return int(f*255), 0, 255
    return 255, 0, int((1-f)*255)
  
# Sets up matrix settings
def setup_matrix():
    options = RGBMatrixOptions()
    options.rows = 64
    options.cols = 64
    options.chain_length = 1
    options.parallel = 1
    options.brightness = 60
    return RGBMatrix(options=options)

# Main class to run on RGB LED matrix
def main(stdscr):
	curses.curs_set(0) # Hides blinking terminal cursor
	stdscr.nodelay(True) # Makes stdscr.getch() non-blocking
	
	pa = pyaudio.PyAudio() # Get audio source from pi
	mic = find_input_audio(pa) # Get the mic source
	stream = pa.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE, input=True, frames_per_buffer=CHUNK, input_device_index=mic,)
	
	matrix = setup_matrix() # Set up matrix
	canvas = matrix.CreateFrameCanvas() # Set up matrix frame
	smoothed = [0.0] * NUM_BARS # Creat list of NUM_BARS zeros, starts at zero
	
	try:
		while True: # Run until user quits
			k = stdscr.getch()
			if k in (ord("q"), ord("Q"), 27): # Escape = key 27
				break
		
			raw = stream.read(CHUNK, exception_on_overflow=False) # Get raw 2048 audio samples from mic
			bars = get_bars(raw, NUM_BARS) # Call our FFT function to get bar percentage
		
			# Apply smoothing to every bar every frame
			for i in range(NUM_BARS):
				if bars[i] > smoothed[i]: 
					# If new value is louder, update it
					smoothed[i] = bars[i]
				else:
					# If new value is quieter, blender the old with the new (difts down)
					# Math behind this: old x SMOOTHING + new x (1- SMOOTHING)
					# Higher SMOOTHING gives slower dreamy falls
					# Lower SMOOTHING gives instant drops
					smoothed[i] = smoothed[i] * SMOOTHING + bars[i] * (1 - SMOOTHING)
			
			# Call our draw function to display the height bars
			draw(canvas, smoothed)
			# Wait for matrix to refresh (VSync), swap hidden canvas to visible display, return old canvas so you can draw into it
			canvas = matrix.SwapOnVSync(canvas)
	finally: # finally runs no matter how the program exits; ensures the mic closes properly, canvas to black, swaps blank canvas in
		stream.stop_stream()
		stream.close()
		pa.terminate()
		canvas.Clear()
		matrix.SwapOnVSync(canvas)

# Run the main method
curses.wrapper(main)


