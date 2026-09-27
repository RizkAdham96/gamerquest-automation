from __future__ import annotations

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one replacement target, found {count}: {old[:80]!r}")
    write(path, text.replace(old, new, 1))


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    text = read(path)
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"{path}: start marker not found: {start!r}")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise RuntimeError(f"{path}: end marker not found: {end!r}")
    write(path, text[:start_index] + replacement + text[end_index:])


RECONCILE_STEP = '''      - name: Reconcile shared Groq budget ({label})
        if: ${{{{ always() && steps.groq_budget.outputs.allowed == 'true' }}}}
        env:
          GROQ_USAGE_FILE: ${{{{ runner.temp }}}}/groq-usage-{slug}.json
        shell: bash
        run: |
          set -euo pipefail
          reservation_id="${{GITHUB_RUN_ID}}-${{GITHUB_RUN_ATTEMPT}}-{slug}"
          used_tokens="$(python - <<'PY'
          import json
          import os
          from pathlib import Path

          path = Path(os.environ["GROQ_USAGE_FILE"])
          used = 0
          if path.exists():
              try:
                  payload = json.loads(path.read_text(encoding="utf-8"))
                  used = max(0, int(payload.get("estimated_tokens", 0) or 0))
              except Exception as exc:
                  print(f"Usage file unreadable; keeping reservation conservative: {{exc}}", file=__import__('sys').stderr)
                  raise SystemExit(2)
          print(used)
          PY
          )"

          git config user.name "GamerQuest Budget Bot"
          git config user.email "actions@github.com"

          for attempt in 1 2 3; do
            echo "{label} budget reconciliation attempt ${{attempt}}/3; used=${{used_tokens}}"
            git fetch origin main
            git reset --hard origin/main

            RESERVATION_ID="${{reservation_id}}" USED_TOKENS="${{used_tokens}}" python - <<'PY'
          import os
          from groq_budget import reconcile_run

          result = reconcile_run(
              os.environ["RESERVATION_ID"],
              int(os.environ["USED_TOKENS"]),
          )
          print(
              "Groq reconciliation: "
              f"reconciled={{result['reconciled']}} "
              f"used={{result['used_tokens']}} "
              f"released={{result['released_tokens']}} "
              f"reason={{result['reason']}}"
          )
          PY

            git add state/groq_budget.json
            if git diff --cached --quiet; then
              echo "No Groq budget state change to persist."
              exit 0
            fi
            git commit -m "budget: reconcile {label} Groq allowance"
            if git push origin HEAD:main; then
              exit 0
            fi
            echo "Shared budget state changed before reconciliation push; retrying safely."
          done

          echo "Unable to persist {label} Groq reconciliation after 3 attempts." >&2
          exit 1
'''


def patch_news() -> None:
    path = ".github/workflows/gamerquest.yml"
    replace_once(
        path,
        '          GROQ_TPM_CEILING: "6000"\n          TAVILY_API_KEY:',
        '          GROQ_TPM_CEILING: "6000"\n          GROQ_USAGE_FILE: ${{ runner.temp }}/groq-usage-news.json\n          TAVILY_API_KEY:',
    )
    text = read(path)
    if "Reconcile shared Groq budget (News)" in text:
        raise RuntimeError("News reconciliation is already wired")
    write(path, text.rstrip() + "\n\n" + RECONCILE_STEP.format(label="News", slug="news"))


def patch_seo() -> None:
    path = ".github/workflows/run-trending-seo-pipeline.yml"
    replace_once(
        path,
        '          GROQ_TPM_CEILING: "6000"\n          WP_URL:',
        '          GROQ_TPM_CEILING: "6000"\n          GROQ_USAGE_FILE: ${{ runner.temp }}/groq-usage-seo.json\n          WP_URL:',
    )
    text = read(path)
    if "Reconcile shared Groq budget (SEO)" in text:
        raise RuntimeError("SEO reconciliation is already wired")
    write(path, text.rstrip() + "\n\n" + RECONCILE_STEP.format(label="SEO", slug="seo"))


def patch_social() -> None:
    path = ".github/workflows/social-test.yml"
    replace_once(
        path,
        "          python tests/social/test_prepare_publish.py\n          python tests/social/test_publish_run.py",
        "          python tests/social/test_prepare_publish.py\n          python tests/social/test_wordpress_publish.py\n          python tests/social/test_publish_run.py",
    )
    replace_once(
        path,
        '          GROQ_TPM_CEILING: "6000"\n        run: python -m social.run_fresh',
        '          GROQ_TPM_CEILING: "6000"\n          GROQ_USAGE_FILE: ${{ runner.temp }}/groq-usage-social.json\n        run: python -m social.run_fresh',
    )

    stage = '''      - name: Stage carousel in temporary WordPress media
        id: wordpress_stage
        if: ${{ github.event_name != 'push' && steps.social_status.outputs.ready == 'true' && (github.event_name == 'schedule' || inputs.publish_to_meta == true) }}
        env:
          PYTHONPATH: .
          WP_URL: ${{ secrets.WP_URL }}
          WP_USERNAME: ${{ secrets.WP_USERNAME }}
          WP_APP_PASSWORD: ${{ secrets.WP_APP_PASSWORD }}
        run: python -m social.wordpress_publish stage

'''
    replace_between(
        path,
        "      - name: Prepare carousel for public publishing\n",
        "      - name: Verify exactly three current carousel images\n",
        stage,
    )
    replace_once(
        path,
        "      - name: Verify exactly three current carousel images\n        if: ${{ github.event_name != 'push' && steps.social_status.outputs.ready == 'true' }}",
        "      - name: Verify exactly three current carousel images\n        if: ${{ github.event_name != 'push' && steps.social_status.outputs.ready == 'true' && (github.event_name == 'schedule' || inputs.publish_to_meta == true) }}",
    )

    pending_commit = '''      - name: Commit pending WordPress publish manifest
        if: ${{ github.event_name != 'push' && steps.wordpress_stage.outcome == 'success' }}
        shell: bash
        run: |
          git config user.name "GamerQuest Social Bot"
          git config user.email "actions@github.com"
          git add social/pending_publish.json
          if git diff --cached --quiet; then
            echo "Pending publish manifest is already current."
          else
            git commit -m "social: persist pending Meta publish package"
            git fetch origin main
            git rebase origin/main
            git push origin HEAD:main
          fi

'''
    replace_between(
        path,
        "      - name: Commit prepared carousel\n",
        "      - name: Snapshot whether Meta publish is actually pending\n",
        pending_commit,
    )

    cleanup = '''      - name: Clean temporary WordPress carousel media
        id: wordpress_cleanup
        if: ${{ steps.meta_publish.outcome == 'success' }}
        env:
          PYTHONPATH: .
          WP_URL: ${{ secrets.WP_URL }}
          WP_USERNAME: ${{ secrets.WP_USERNAME }}
          WP_APP_PASSWORD: ${{ secrets.WP_APP_PASSWORD }}
        run: python -m social.wordpress_publish cleanup

'''
    replace_once(
        path,
        "      - name: Commit Meta publish history\n",
        cleanup + "      - name: Commit Meta publish history\n",
    )

    commit_block = '''      - name: Commit Meta publish history
        if: ${{ always() && steps.social_status.outputs.ready == 'true' && (github.event_name == 'schedule' || inputs.publish_to_meta == true) }}
        shell: bash
        run: |
          git config user.name "GamerQuest Social Bot"
          git config user.email "actions@github.com"
          git add -A social/publish_history.json social/pending_publish.json 2>/dev/null || true
          if ! git diff --cached --quiet; then
            git commit -m "social: update Meta publish state"
            git fetch origin main
            git rebase origin/main
            git push origin HEAD:main
          fi

'''
    replace_between(
        path,
        "      - name: Commit Meta publish history\n",
        "      - name: P0 social final status\n",
        commit_block + RECONCILE_STEP.format(label="Social", slug="social") + "\n",
    )

    replace_once(
        path,
        '''          elif [ "${PUBLISH_REQUESTED}" = "true" ] && [ "${{ steps.meta_preflight.outcome }}" = "failure" ]; then
            RESULT="FAILED"
            REASON="Meta preflight failed before any publishing attempt."
          elif [ "${{ steps.groq_budget.outputs.allowed }}" != "true" ]; then''',
        '''          elif [ "${PUBLISH_REQUESTED}" = "true" ] && [ "${{ steps.meta_preflight.outcome }}" = "failure" ]; then
            RESULT="FAILED"
            REASON="Meta preflight failed before any publishing attempt."
          elif [ "${PUBLISH_REQUESTED}" = "true" ] && [ "${{ steps.wordpress_stage.outcome }}" = "failure" ]; then
            RESULT="FAILED"
            REASON="Temporary WordPress media staging failed; nothing was sent to Meta."
          elif [ "${{ steps.groq_budget.outputs.allowed }}" != "true" ]; then''',
    )
    replace_once(
        path,
        '''            echo "Meta preflight: ${{ steps.meta_preflight.outcome }}"
            echo "Meta pending before publish: ${{ steps.meta_pending.outputs.pending_platforms }}"
            echo "Meta publish: ${{ steps.meta_publish.outcome }}"''',
        '''            echo "Meta preflight: ${{ steps.meta_preflight.outcome }}"
            echo "WordPress staging: ${{ steps.wordpress_stage.outcome }}"
            echo "Meta pending before publish: ${{ steps.meta_pending.outputs.pending_platforms }}"
            echo "Meta publish: ${{ steps.meta_publish.outcome }}"
            echo "WordPress cleanup: ${{ steps.wordpress_cleanup.outcome }}"''',
    )
    replace_once(
        path,
        '''            social-rendered/
            social-published/
            social/publish_history.json
          if-no-files-found: warn''',
        '''            social-rendered/
            social/publish_history.json
          if-no-files-found: warn
          retention-days: 3''',
    )


def patch_recovery() -> None:
    path = ".github/workflows/social-publish-recovery.yml"
    guard = '''      - name: Check for a pending WordPress Meta package
        id: guard
        shell: bash
        run: |
          python - <<'PY'
          import json
          import os
          from pathlib import Path

          pending_path = Path("social/pending_publish.json")
          should_recover = False
          reason = "no pending WordPress carousel"
          if pending_path.exists():
              try:
                  payload = json.loads(pending_path.read_text(encoding="utf-8"))
                  urls = payload.get("image_urls", []) if isinstance(payload, dict) else []
                  media_ids = payload.get("media_ids", []) if isinstance(payload, dict) else []
                  should_recover = (
                      isinstance(payload, dict)
                      and bool(str(payload.get("source_id", "")).strip())
                      and bool(str(payload.get("carousel_version", "")).strip())
                      and len(urls) == 3
                      and len(set(urls)) == 3
                      and len(media_ids) == 3
                  )
                  reason = "valid pending WordPress carousel" if should_recover else "pending WordPress manifest is invalid"
              except Exception as exc:
                  reason = f"pending WordPress manifest unreadable: {exc}"

          print(f"Recovery required: {should_recover}; reason={reason}")
          with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
              output.write(f"should_recover={'true' if should_recover else 'false'}\\n")
              output.write(f"reason={reason.replace(chr(10), ' ')}\\n")
          PY

'''
    replace_between(
        path,
        "      - name: Check whether Instagram already published today\n",
        "  recover-social-publish:\n",
        guard,
    )
    replace_once(
        path,
        "          python tests/social/test_prepare_publish.py\n          python tests/social/test_publish_run.py",
        "          python tests/social/test_prepare_publish.py\n          python tests/social/test_wordpress_publish.py\n          python tests/social/test_publish_run.py",
    )
    replace_once(
        path,
        "      - name: Retry Meta publish from committed carousel\n",
        "      - name: Retry Meta publish from pending WordPress carousel\n",
    )

    cleanup = '''      - name: Clean recovered WordPress carousel media
        id: wordpress_cleanup
        if: ${{ steps.meta_publish.outcome == 'success' }}
        env:
          PYTHONPATH: .
          WP_URL: ${{ secrets.WP_URL }}
          WP_USERNAME: ${{ secrets.WP_USERNAME }}
          WP_APP_PASSWORD: ${{ secrets.WP_APP_PASSWORD }}
        run: python -m social.wordpress_publish cleanup

'''
    replace_once(
        path,
        "      - name: Commit Meta publish history\n",
        cleanup + "      - name: Commit Meta publish history\n",
    )
    commit_block = '''      - name: Commit Meta publish history
        if: ${{ always() && steps.recovery_package.outputs.ready == 'true' }}
        shell: bash
        run: |
          git config user.name "GamerQuest Social Bot"
          git config user.email "actions@github.com"
          git add -A social/publish_history.json social/pending_publish.json 2>/dev/null || true
          if ! git diff --cached --quiet; then
            git commit -m "social: update Meta publish state (recovery)"
            git fetch origin main
            git rebase origin/main
            git push origin HEAD:main
          fi

'''
    replace_between(
        path,
        "      - name: Commit Meta publish history\n",
        "      - name: Report recovery result\n",
        commit_block,
    )
    replace_once(
        path,
        '''          echo "Meta publish: ${{ steps.meta_publish.outcome }}" >> "${GITHUB_STEP_SUMMARY}"''',
        '''          echo "Meta publish: ${{ steps.meta_publish.outcome }}" >> "${GITHUB_STEP_SUMMARY}"
          echo "WordPress cleanup: ${{ steps.wordpress_cleanup.outcome }}" >> "${GITHUB_STEP_SUMMARY}"''',
    )


def add_wordpress_test() -> None:
    path = ROOT / "tests/social/test_wordpress_publish.py"
    path.write_text('''import json\nimport tempfile\nimport unittest\nfrom pathlib import Path\nfrom unittest.mock import patch\n\nfrom social.wordpress_publish import (\n    cleanup_publish_package,\n    recover_publish_package,\n    stage_publish_package,\n)\n\n\nclass WordPressPublishPackageTests(unittest.TestCase):\n    def test_stage_recover_cleanup_round_trip(self):\n        with tempfile.TemporaryDirectory() as tmp:\n            root = Path(tmp)\n            rendered = root / "rendered"\n            rendered.mkdir()\n            for index in range(1, 4):\n                (rendered / f"slide-{index}.png").write_bytes((f"slide-{index}-" * 30).encode())\n\n            ready = root / "ready.json"\n            pending = root / "pending.json"\n            output = root / "output.json"\n            social_output = {"status": "ready", "source_id": "source-123", "caption": "ok"}\n            staged = {\n                "image_urls": [f"https://example.test/{i}.png" for i in range(1, 4)],\n                "media_ids": [101, 102, 103],\n            }\n\n            with patch("social.wordpress_publish.stage_carousel_media", return_value=staged) as upload:\n                package = stage_publish_package(\n                    social_output=social_output,\n                    rendered_dir=rendered,\n                    ready_file=ready,\n                    pending_file=pending,\n                    wp_url="https://example.test",\n                    username="user",\n                    app_password="pass",\n                )\n            self.assertEqual(package["image_urls"], staged["image_urls"])\n            self.assertEqual(package["media_ids"], staged["media_ids"])\n            self.assertTrue(ready.exists())\n            self.assertTrue(pending.exists())\n            upload.assert_called_once()\n\n            restored_ready = root / "restored-ready.json"\n            recovered = recover_publish_package(\n                pending_file=pending,\n                output_file=output,\n                ready_file=restored_ready,\n            )\n            self.assertTrue(recovered["ready"])\n            self.assertEqual(json.loads(restored_ready.read_text())["image_urls"], staged["image_urls"])\n\n            with patch("social.wordpress_publish.cleanup_media") as cleanup:\n                result = cleanup_publish_package(\n                    pending_file=pending,\n                    wp_url="https://example.test",\n                    username="user",\n                    app_password="pass",\n                )\n            self.assertTrue(result["cleaned"])\n            self.assertFalse(pending.exists())\n            cleanup.assert_called_once_with(\n                staged["media_ids"],\n                wp_url="https://example.test",\n                username="user",\n                app_password="pass",\n            )\n\n\nif __name__ == "__main__":\n    unittest.main()\n''', encoding="utf-8")


def add_gitignore() -> None:
    path = ROOT / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    block = '''\n# GamerQuest generated runtime artifacts\nacquisition/shadow_queue.json\nsocial-rendered/\nsocial-published/\nsocial-output.json\nsocial-publish-ready.json\n'''
    if "acquisition/shadow_queue.json" not in existing:
        path.write_text(existing.rstrip() + block + "\n", encoding="utf-8")


def remove_stale_runtime_assets() -> None:
    stale_file = ROOT / "acquisition/shadow_queue.json"
    stale_file.unlink(missing_ok=True)
    stale_dir = ROOT / "social-published"
    if stale_dir.exists():
        shutil.rmtree(stale_dir)


def remove_bootstrap_files() -> None:
    (ROOT / ".github/workflows/apply-production-hardening.yml").unlink(missing_ok=True)
    Path(__file__).unlink(missing_ok=True)


def main() -> None:
    patch_news()
    patch_seo()
    patch_social()
    patch_recovery()
    add_wordpress_test()
    add_gitignore()
    remove_stale_runtime_assets()
    remove_bootstrap_files()
    print("Production hardening patch applied successfully.")


if __name__ == "__main__":
    main()
