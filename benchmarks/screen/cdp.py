"""Minimal local Chrome DevTools client; owns only the tab it opens."""
import base64, json, urllib.request
import websocket
CDP = ''
class Tab:
    def __init__(self):
        req = urllib.request.Request(CDP + '/json/new?about:blank', method='PUT')
        info = json.loads(urllib.request.urlopen(req, timeout=10).read())
        self.id = info['id']
        self.ws = websocket.create_connection(info['webSocketDebuggerUrl'], timeout=30, suppress_origin=True)
        self.n = 0

    def call(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({'id': self.n, 'method': method, 'params': params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get('id') == self.n:
                if 'error' in msg:
                    raise RuntimeError(f'{method}: {msg["error"]}')
                return msg.get('result', {})

    def shot(self):
        return base64.b64decode(self.call('Page.captureScreenshot', format='png')['data'])

    def title(self):  # window title (what a desktop agent reads from the window manager)
        return self.call('Target.getTargetInfo', targetId=self.id)['targetInfo']['title']

    def click(self, x, y):
        self.call('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y)
        self.call('Input.dispatchMouseEvent', type='mousePressed', x=x, y=y, button='left', clickCount=1)
        self.call('Input.dispatchMouseEvent', type='mouseReleased', x=x, y=y, button='left', clickCount=1)

    def type(self, text):
        self.call('Input.dispatchKeyEvent', type='keyDown', key='a', code='KeyA', commands=['selectAll'])
        self.call('Input.dispatchKeyEvent', type='keyUp', key='a', code='KeyA')
        self.call('Input.insertText', text=text)

    def close(self):
        try:
            self.ws.close()
            urllib.request.urlopen(CDP + '/json/close/' + self.id, timeout=5).read()
        except Exception:
            pass
