import json
from pathlib import Path

from acquisition.run_shadow import main


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_cli_writes_shadow_queue(tmp_path, capsys):
    _write_json(
        tmp_path / "trending_seo" / "intel" / "topics.json",
        {
            "topics": [
                {
                    "id": "save-error",
                    "topic": "Monster Hunter Wilds erreur sauvegarde PC comment corriger",
                    "keywords": ["Monster Hunter Wilds erreur sauvegarde PC"],
                    "status": "new",
                    "sources": [{"type": "official"}],
                }
            ]
        },
    )

    output = tmp_path / "acquisition" / "shadow_queue.json"
    exit_code = main(root=tmp_path, output_path=output)

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["mode"] == "shadow"
    assert payload["count"] == 1
    assert payload["opportunities"][0]["id"] == "save-error"
    assert "GAMERQUEST ACQUISITION SHADOW" in capsys.readouterr().out
