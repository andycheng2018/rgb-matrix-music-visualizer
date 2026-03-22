#!/usr/bin/env python3
import time
import random
import curses

from rgbmatrix import RGBMatrix, RGBMatrixOptions

# -----------------------
# CONFIG
# -----------------------
TILE = 2          # 64x64 => 32x32 tiles
FPS = 20
GHOST_SLOW = 2    # ghost moves every N ticks

LEVEL = [
"############################",
"#............##............#",
"#.####.#####.##.#####.####.#",
"#.####.#####.##.#####.####.#",
"#..........................#",
"#.####.##.########.##.####.#",
"#......##....##....##......#",
"######.##### ## #####.######",
"     #.##### ## #####.#     ",
"######.##          ##.######",
"#......## ######## ##......#",
"#.####.## ######## ##.####.#",
"#.####.##          ##.####.#",
"#............##............#",
"#.####.#####.##.#####.####.#",
"#...##................##...#",
"###.##.##.########.##.##.###",
"#......##....##....##......#",
"#.##########.##.##########.#",
"#..........................#",
"#.####.#####.##.#####.####.#",
"#.####.#####.##.#####.####.#",
"#............##............#",
"############################",
]

W = max(len(r) for r in LEVEL)
LEVEL = [r.ljust(W) for r in LEVEL]
H = len(LEVEL)

VIEW_TW, VIEW_TH = 32, 32
OFF_X = (VIEW_TW - W) // 2
OFF_Y = (VIEW_TH - H) // 2

DIRS = {
    "UP": (0, -1),
    "DOWN": (0, 1),
    "LEFT": (-1, 0),
    "RIGHT": (1, 0),
}
OPPOSITE = {"UP": "DOWN", "DOWN": "UP", "LEFT": "RIGHT", "RIGHT": "LEFT"}


def clamp(n, a, b):
    return max(a, min(b, n))


def is_wall(x, y):
    if x < 0 or y < 0 or x >= W or y >= H:
        return True
    return LEVEL[y][x] == "#"


def draw_tile(canvas, tx, ty, color):
    px = tx * TILE
    py = ty * TILE
    r, g, b = color
    for dy in range(TILE):
        for dx in range(TILE):
            canvas.SetPixel(px + dx, py + dy, r, g, b)


# --- Tiny 5x7 font for end screens (only letters we need) ---
FONT_5x7 = {
    "A": ["01110","10001","10001","11111","10001","10001","10001"],
    "E": ["11111","10000","10000","11110","10000","10000","11111"],
    "G": ["01111","10000","10000","10011","10001","10001","01111"],
    "I": ["11111","00100","00100","00100","00100","00100","11111"],
    "M": ["10001","11011","10101","10101","10001","10001","10001"],
    "N": ["10001","11001","10101","10011","10001","10001","10001"],
    "O": ["01110","10001","10001","10001","10001","10001","01110"],
    "R": ["11110","10001","10001","11110","10100","10010","10001"],
    "U": ["10001","10001","10001","10001","10001","10001","01110"],
    "V": ["10001","10001","10001","10001","10001","01010","00100"],
    "W": ["10001","10001","10001","10101","10101","10101","01010"],
    "Y": ["10001","10001","01010","00100","00100","00100","00100"],
    " ": ["00000","00000","00000","00000","00000","00000","00000"],
}


def draw_text_5x7(canvas, x, y, text, color):
    """Draw 5x7 font at pixel coords (x,y)."""
    r, g, b = color
    cx = x
    for ch in text:
        glyph = FONT_5x7.get(ch.upper(), FONT_5x7[" "])
        for row in range(7):
            bits = glyph[row]
            for col in range(5):
                if bits[col] == "1":
                    canvas.SetPixel(cx + col, y + row, r, g, b)
        cx += 6  # 5 pixels + 1 spacing


def draw_centered_message(canvas, line1, line2, color):
    """
    Center two lines using 5x7 font.
    Each char is 6px wide; height is 7px.
    """
    canvas.Clear()
    w1 = len(line1) * 6 - 1
    w2 = len(line2) * 6 - 1
    x1 = (64 - w1) // 2
    x2 = (64 - w2) // 2
    y1 = 22
    y2 = 34
    draw_text_5x7(canvas, x1, y1, line1, color)
    draw_text_5x7(canvas, x2, y2, line2, color)


def show_end_screen(matrix, stdscr, won, score):
    """
    Blink end screen. Quit with Q / ESC.
    """
    canvas = matrix.CreateFrameCanvas()
    line1 = "YOU WIN" if won else "GAME OVER"
    line2 = "PRESS Q"

    color = (0, 255, 0) if won else (255, 0, 0)

    stdscr.nodelay(True)
    stdscr.keypad(True)

    blink = True
    last = time.time()

    while True:
        k = stdscr.getch()
        if k in (ord("q"), ord("Q"), 27):
            break

        now = time.time()
        if now - last > 0.5:
            blink = not blink
            last = now

        if blink:
            draw_centered_message(canvas, line1, line2, color)
        else:
            canvas.Clear()

        # tiny score bar at bottom (optional)
        bar = clamp(score // 50, 0, 60)
        for x in range(bar):
            canvas.SetPixel(2 + x, 63, 255, 255, 0)

        canvas = matrix.SwapOnVSync(canvas)


class Game:
    def __init__(self):
        self.pellets = [[(LEVEL[y][x] == ".") for x in range(W)] for y in range(H)]
        self.total_pellets = sum(sum(1 for v in row if v) for row in self.pellets)

        self.px, self.py = self.find_spawn()
        self.pdir = "LEFT"
        self.buffer_dir = "LEFT"

        self.gx, self.gy = self.find_spawn(prefer_center=True)
        self.gdir = "RIGHT"

        self.score = 0
        self.lives = 3
        self.tick = 0
        self.won = False

    def find_spawn(self, prefer_center=False):
        spots = [(x, y) for y in range(H) for x in range(W) if not is_wall(x, y)]
        if not spots:
            return 1, 1
        if prefer_center:
            cx, cy = W // 2, H // 2
            spots.sort(key=lambda p: abs(p[0] - cx) + abs(p[1] - cy))
        return spots[0]

    def try_move(self, x, y, d):
        dx, dy = DIRS[d]
        nx, ny = x + dx, y + dy
        if not is_wall(nx, ny):
            return nx, ny
        return x, y

    def update_player(self):
        nx, ny = self.try_move(self.px, self.py, self.buffer_dir)
        if (nx, ny) != (self.px, self.py):
            self.pdir = self.buffer_dir

        self.px, self.py = self.try_move(self.px, self.py, self.pdir)

        if 0 <= self.px < W and 0 <= self.py < H and self.pellets[self.py][self.px]:
            self.pellets[self.py][self.px] = False
            self.score += 10
            self.total_pellets -= 1
            if self.total_pellets == 0:
                self.won = True

    def ghost_neighbors(self, x, y):
        opts = []
        for d, (dx, dy) in DIRS.items():
            nx, ny = x + dx, y + dy
            if not is_wall(nx, ny):
                opts.append((d, nx, ny))
        return opts

    def update_ghost(self):
        opts = self.ghost_neighbors(self.gx, self.gy)
        if not opts:
            return

        filtered = [o for o in opts if o[0] != OPPOSITE.get(self.gdir)]
        if filtered:
            opts = filtered

        if random.random() < 0.7:
            opts.sort(key=lambda o: abs(o[1] - self.px) + abs(o[2] - self.py))
            choice = opts[0]
        else:
            choice = random.choice(opts)

        self.gdir, self.gx, self.gy = choice

    def check_collisions(self):
        if (self.px, self.py) == (self.gx, self.gy):
            self.lives -= 1
            if self.lives <= 0:
                return
            self.px, self.py = self.find_spawn()
            self.pdir = "LEFT"
            self.buffer_dir = "LEFT"
            self.gx, self.gy = self.find_spawn(prefer_center=True)
            self.gdir = "RIGHT"

    def update(self):
        self.tick += 1
        self.update_player()
        if self.won:
            return
        if self.tick % GHOST_SLOW == 0:
            self.update_ghost()
        self.check_collisions()

    def draw(self, canvas):
        canvas.Clear()

        for y in range(H):
            for x in range(W):
                vx = x + OFF_X
                vy = y + OFF_Y
                if 0 <= vx < VIEW_TW and 0 <= vy < VIEW_TH:
                    if LEVEL[y][x] == "#":
                        draw_tile(canvas, vx, vy, (0, 0, 255))
                    elif self.pellets[y][x]:
                        px = vx * TILE + TILE // 2
                        py = vy * TILE + TILE // 2
                        canvas.SetPixel(px, py, 255, 255, 255)

        pvx, pvy = self.px + OFF_X, self.py + OFF_Y
        if 0 <= pvx < VIEW_TW and 0 <= pvy < VIEW_TH:
            draw_tile(canvas, pvx, pvy, (255, 255, 0))

        gvx, gvy = self.gx + OFF_X, self.gy + OFF_Y
        if 0 <= gvx < VIEW_TW and 0 <= gvy < VIEW_TH:
            draw_tile(canvas, gvx, gvy, (255, 0, 0))

        for i in range(max(0, self.lives)):
            canvas.SetPixel(2 + i * 2, 0, 0, 255, 0)

        bar = clamp(self.score // 50, 0, 60)
        for x in range(bar):
            canvas.SetPixel(2 + x, 63, 255, 255, 0)


def setup_matrix():
    options = RGBMatrixOptions()
    options.rows = 64
    options.cols = 64
    options.chain_length = 1
    options.parallel = 1
    options.brightness = 60

    # If your demo needed these, uncomment:
    # options.hardware_mapping = "adafruit-hat"  # or "regular"
    # options.gpio_slowdown = 4

    return RGBMatrix(options=options)


def main(stdscr):
    stdscr.nodelay(True)
    stdscr.keypad(True)
    curses.curs_set(0)

    matrix = setup_matrix()
    canvas = matrix.CreateFrameCanvas()

    g = Game()
    dt = 1.0 / FPS
    last = time.time()

    while True:
        # Input
        k = stdscr.getch()
        if k in (curses.KEY_UP, ord("w")):
            g.buffer_dir = "UP"
        elif k in (curses.KEY_DOWN, ord("s")):
            g.buffer_dir = "DOWN"
        elif k in (curses.KEY_LEFT, ord("a")):
            g.buffer_dir = "LEFT"
        elif k in (curses.KEY_RIGHT, ord("d")):
            g.buffer_dir = "RIGHT"
        elif k in (ord("q"), 27):
            break

        now = time.time()
        if now - last >= dt:
            last = now
            g.update()
            g.draw(canvas)
            canvas = matrix.SwapOnVSync(canvas)

            if g.won:
                show_end_screen(matrix, stdscr, won=True, score=g.score)
                break
            if g.lives <= 0:
                show_end_screen(matrix, stdscr, won=False, score=g.score)
                break

    canvas.Clear()
    matrix.SwapOnVSync(canvas)


if __name__ == "__main__":
    curses.wrapper(main)