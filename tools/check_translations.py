#!/usr/bin/env python3
"""Check README translations against the English README (the reference).

    python tools/check_translations.py            # check README.ko.md and README.ja.md
    python tools/check_translations.py --stamp    # after updating a translation, record the English README hash in it

For each translation:
- every number in README.md appears at least as many times in the translation (code included); an EXTRA number in the
  translation fails unless it is a single digit 1-9 (languages such as Japanese write counts as digits: "2 つ" for "two"),
  so a changed value (59 -> 60) still fails twice: missing 59, extra 60;
- the set of link targets (href="..." and markdown (...) links) is the same, apart from the language-switch links;
- the translation's `source-sha256` comment matches the current README.md. If README.md changed after the translation was
  last updated, the check prints "update needed" and exits 1.
Exit 0 = all translations match and are up to date.
"""
import hashlib
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "README.md"
TRANSLATIONS = [ROOT / "README.ko.md", ROOT / "README.ja.md"]
LANG_LINE = re.compile(r'^<p align="center">(<a href="README(\.\w\w)?\.md">|<b>)')
NUM = re.compile(r"\d+(?:[.,]\d+)*")
LINK = re.compile(r'href="([^"]+)"|\]\(([^)\s]+)\)')
STAMP = re.compile(r"<!-- source-sha256: ([0-9a-f]{64}) -->")


def body(text):
    return "\n".join(l for l in text.splitlines() if not LANG_LINE.match(l) and not STAMP.search(l))


def numbers(text):
    return Counter(n.replace(",", "") for n in NUM.findall(body(text)))


def links(text):
    out = set()
    for a, b in LINK.findall(body(text)):
        t = a or b
        if t.startswith("#"):
            continue  # in-page anchors differ by language (heading text)
        out.add(t)
    return out


def main():
    ref_text = REF.read_text(encoding="utf-8")
    ref_sha = hashlib.sha256(REF.read_bytes()).hexdigest()
    ok = True
    for p in TRANSLATIONS:
        if not p.exists():
            print(f"{p.name}: missing")
            ok = False
            continue
        t = p.read_text(encoding="utf-8")
        if "--stamp" in sys.argv:
            line = f"<!-- source-sha256: {ref_sha} -->"
            t = STAMP.sub(line, t) if STAMP.search(t) else t.replace("\n\n", "\n\n" + line + "\n\n", 1)
            p.write_text(t, encoding="utf-8")
        extra = numbers(t) - numbers(ref_text)
        dn = numbers(ref_text) - numbers(t), Counter({k: v for k, v in extra.items() if not (len(k) == 1 and k in "123456789")})
        dl = links(ref_text) - links(t), links(t) - links(ref_text)
        m = STAMP.search(t)
        fresh = bool(m) and m.group(1) == ref_sha
        good = not any(dn) and not any(dl) and fresh
        ok &= good
        print(f"{p.name}: {'OK' if good else 'FAIL'}"
              + ("" if not dn[0] else f" | numbers missing {dict(dn[0])}") + ("" if not dn[1] else f" | numbers extra {dict(dn[1])}")
              + ("" if not dl[0] else f" | links missing {sorted(dl[0])}") + ("" if not dl[1] else f" | links extra {sorted(dl[1])}")
              + ("" if fresh else " | update needed (README.md changed since this translation)"))
    ok &= check_page()
    sys.exit(0 if ok else 1)


def check_page():
    """Project page (web/index.html + web/i18n.js): every data-i18n key has a Korean and a Japanese text, and each text has
    the same numbers (single digits 1-9 may be added) and the same link targets as the English text in index.html."""
    import json
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "web" / "i18n.js").read_text(encoding="utf-8")
    en = {}
    for m in re.finditer(r'<(\w+)[^>]*?data-i18n="([^"]+)"[^>]*>', html):
        tag, key, depth, i = m.group(1), m.group(2), 1, m.end()
        while depth:
            o, c = html.find("<" + tag, i), html.find("</" + tag + ">", i)
            if o != -1 and o < c and html[o + len(tag) + 1] in " >":
                depth, i = depth + 1, o + 1
            else:
                depth, i = depth - 1, c + len(tag) + 3
        en[key] = html[m.end():i - len(tag) - 3]
    start = js.index("var T = ") + len("var T = ")
    tables = json.loads(js[start:js.index("};\n  var EN") + 1])
    ok = True
    for lang, t in tables.items():
        bad = []
        for k, v in en.items():
            if k not in t:
                bad.append(f"{k}: missing")
                continue
            ne, nt = Counter(n.replace(",", "") for n in NUM.findall(v)), Counter(n.replace(",", "") for n in NUM.findall(t[k]))
            extra = Counter({x: c for x, c in (nt - ne).items() if not (len(x) == 1 and x in "123456789")})
            le, lt = set(re.findall(r'href="([^"]+)"', v)), set(re.findall(r'href="([^"]+)"', t[k]))
            if ne - nt or extra or le != lt:
                bad.append(f"{k}: numbers missing {dict(ne - nt)} extra {dict(extra)} links {sorted(le ^ lt)}")
        for k in t:
            if not k.startswith("_") and k not in en:
                bad.append(f"{k}: not on the page")
        ok &= not bad
        print(f"web/i18n.js [{lang}]: {'OK' if not bad else 'FAIL'} ({len(en)} keys)" + ("" if not bad else " | " + " ; ".join(bad[:6])))
    return ok


if __name__ == "__main__":
    main()
