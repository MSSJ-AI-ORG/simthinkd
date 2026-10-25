"""A small synthetic screen app for the router example: no browser, no network, NumPy only.

One fixed task, the same shape as task T1/T3 of experiment v2.1: sign in, save a profile form, close an error dialog
and save again (0 to 2 errors), then the "saved" page.

    states   LOGIN -> PROFILE -> (ERROR -> PROFILE)* -> DONE
    actions  FILL_LOGIN, SUBMIT, CLOSE, DISMISS (notice banner), CONTINUE (session page), STOP

Screens are 256 x 192 RGB arrays drawn from rectangles. Everything comes from (layout, seed): the same seed gives the
same screens, errors and small layout jitter (local variation: buttons move a few pixels, colours shift a little, a
grey toast may appear). Two disturbances never appear in training: a yellow notice banner that covers the save button
(pressing it then does nothing) and a session-expired page (both as in v2.1). Layout B is a redesign: other places,
colours and window titles.

`App.truth` is the true state. Only the teacher and the scoring read it; the router sees pixels, title and previous action.
"""
import hashlib

import numpy as np

W, H = 256, 192
STATES = ['LOGIN', 'PROFILE', 'ERROR', 'DONE']
ACTIONS = ['FILL_LOGIN', 'SUBMIT', 'CLOSE', 'DISMISS', 'CONTINUE', 'STOP']
POLICY = {'LOGIN': 'FILL_LOGIN', 'PROFILE': 'SUBMIT', 'ERROR': 'CLOSE', 'DONE': 'STOP', 'BANNER': 'DISMISS', 'SESSION': 'CONTINUE'}
START = ['LOGIN']

LAYOUTS = {
    'A': {'titles': {'LOGIN': 'Sign in', 'PROFILE': 'Profile', 'ERROR': 'Profile', 'DONE': 'Saved', 'SESSION': 'Session expired'},
          'bg': (246, 246, 246), 'bar': (40, 90, 200), 'card': (255, 255, 255), 'card_xy': (64, 40), 'card_wh': (128, 120),
          'button': (40, 90, 200), 'save': (40, 160, 70), 'done': (40, 160, 70)},
    'B': {'titles': {'LOGIN': 'Log in to Portal', 'PROFILE': 'Account details', 'ERROR': 'Account details', 'DONE': 'All set',
                     'SESSION': 'Please sign in again'},
          'bg': (30, 34, 44), 'bar': (150, 60, 170), 'card': (220, 220, 228), 'card_xy': (20, 60), 'card_wh': (150, 110),
          'button': (230, 120, 30), 'save': (150, 60, 170), 'done': (230, 120, 30)},
}


def rng_for(*parts):
    digest = hashlib.sha256('|'.join(map(str, parts)).encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], 'little'))


def _rect(img, x, y, w, h, color):
    x0, y0 = max(0, int(x)), max(0, int(y))
    img[y0:max(y0, int(y + h)), x0:max(x0, int(x + w))] = color


def _shift(color, d):
    return tuple(int(min(255, max(0, c + d))) for c in color)


class App:
    """One run of the task. perturb: 'none', 'banner' (covers the save button once) or 'session' (after the first action)."""

    def __init__(self, layout='A', seed=0, perturb='none', vary=True):
        self.layout, self.seed, self.perturb = LAYOUTS[layout], seed, perturb
        r = rng_for('app', layout, seed)
        self.errors = int(r.integers(0, 3))
        self.jx, self.jy = (int(r.integers(-8, 9)), int(r.integers(-6, 7))) if vary else (0, 0)
        self.tint = int(r.integers(-10, 11)) if vary else 0
        self.toast = bool(vary and r.random() < 0.3)
        self.state, self.overlay, self.actions_done, self.duplicate = 'LOGIN', None, 0, False
        self.banner_left = perturb == 'banner'
        self.session_left = perturb == 'session'

    @property
    def truth(self):
        """True screen for the teacher: the overlay if one is showing, else the state."""
        return self.overlay or self.state

    def title(self):
        return self.layout['titles']['SESSION' if self.overlay == 'SESSION' else self.state]

    def screen(self):
        L, t = self.layout, self.tint
        img = np.empty((H, W, 3), np.uint8)
        img[:] = L['bg']
        _rect(img, 0, 0, W, 16, _shift(L['bar'], t))
        if self.overlay == 'SESSION':
            img[:] = (90, 90, 96)
            _rect(img, 72, 70, 112, 52, (250, 250, 250))
            _rect(img, 100, 104, 56, 12, (240, 140, 30))
            return img
        cx, cy = L['card_xy'][0] + self.jx, L['card_xy'][1] + self.jy
        cw, ch = L['card_wh']
        _rect(img, cx, cy, cw, ch, L['card'])
        if self.state == 'LOGIN':
            for k in range(2):
                _rect(img, cx + 12, cy + 18 + 26 * k, cw - 24, 14, (200, 200, 200))
            _rect(img, cx + 30, cy + 80, cw - 60, 16, _shift(L['button'], t))
        elif self.state in ('PROFILE', 'ERROR'):
            for k in range(3):
                _rect(img, cx + 12, cy + 10 + 22 * k, cw - 24, 12, (205, 205, 205))
            _rect(img, cx + 30, cy + 90, cw - 60, 16, _shift(L['save'], t))
            if self.state == 'ERROR':
                _rect(img, cx + 8, cy + 24, cw - 16, 60, (255, 255, 255))
                _rect(img, cx + 8, cy + 24, cw - 16, 14, (210, 40, 40))
                _rect(img, cx + 44, cy + 64, cw - 88, 12, (120, 120, 120))
        elif self.state == 'DONE':
            _rect(img, cx + 34, cy + 24, cw - 68, cw - 68, _shift(L['done'], t))
        if self.overlay == 'BANNER':
            _rect(img, 0, cy + 84, W, 26, (250, 210, 40))
            _rect(img, W - 50, cy + 90, 40, 14, (60, 60, 60))
        if self.toast:
            _rect(img, W - 70, H - 26, 62, 18, (120, 120, 120))
        return img

    def observe(self, prev):
        """What the router sees, plus the truth for the teacher and the scoring (the adapter ignores 'truth')."""
        return {'pixels': self.screen(), 'title': self.title(), 'prev': prev, 'truth': self.truth}

    def do(self, action):
        """Apply one action. A wrong action changes nothing (like a click that hits nothing), except SUBMIT on a page that
        is already DONE, which records a duplicate (a task failure)."""
        self.actions_done += 1
        if self.overlay == 'SESSION':
            if action == 'CONTINUE':
                self.overlay = None
            return
        if self.overlay == 'BANNER':
            if action == 'DISMISS':
                self.overlay = None
            return
        if self.state == 'LOGIN' and action == 'FILL_LOGIN':
            self.state = 'PROFILE'
        elif self.state == 'PROFILE' and action == 'SUBMIT':
            if self.errors:
                self.errors -= 1
                self.state = 'ERROR'
            else:
                self.state = 'DONE'
        elif self.state == 'ERROR' and action == 'CLOSE':
            self.state = 'PROFILE'
        elif self.state == 'DONE' and action == 'SUBMIT':
            self.duplicate = True
        if self.session_left and self.actions_done == 1:
            self.session_left, self.overlay = False, 'SESSION'
        elif self.banner_left and self.state == 'PROFILE':
            self.banner_left, self.overlay = False, 'BANNER'

    @property
    def success(self):
        return self.state == 'DONE' and self.overlay is None and not self.duplicate
