import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))

from fix_mojibake_v1 import repair_fully  # noqa: E402


def test_double_encoded_text_is_repaired_and_real_characters_stay():
    broken = "PDVM Passwort zurÃ¼cksetzen, GÃ¼ltigkeit, Ã¤ndern, grÃ¶ÃŸer"
    assert repair_fully(broken)[0] == "PDVM Passwort zurücksetzen, Gültigkeit, ändern, größer"
    assert repair_fully("richtig: ü ä ✅ – €")[0] == "richtig: ü ä ✅ – €"  # nichts zu tun
    assert repair_fully("Ã¼ und ✅")[0] == "ü und ✅"  # gemischt: nur die kaputte Folge wird repariert


def test_emoji_mojibake_is_repaired():
    assert repair_fully("ðŸ”§ Wartung")[0] == "🔧 Wartung"
    assert repair_fully("Zeile")[1] == 0
