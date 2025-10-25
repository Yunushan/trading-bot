from pathlib import Path
text = Path(r"app/gui/main_window.py").read_text()
start = text.index('df = wrapper.get_klines(')
print(text[start:start+100])
