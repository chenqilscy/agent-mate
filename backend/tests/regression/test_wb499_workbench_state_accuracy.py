from pathlib import Path
import subprocess
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[3]


class WorkbenchStateAccuracyTests(unittest.TestCase):
    def test_run_selection_and_domain_merge_execute_real_typescript_helpers(self) -> None:
        script = textwrap.dedent(
            r"""
            const fs = require('fs');
            const ts = require('typescript');
            const source = fs.readFileSync('src/lib/workbench.ts', 'utf8');
            const output = ts.transpileModule(source, {
              compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
            }).outputText;
            const compiled = { exports: {} };
            new Function('exports', 'module', 'require', output)(compiled.exports, compiled, require);
            const { selectCurrentWorkbenchRuns, mergeWorkbenchDomains } = compiled.exports;

            const run = (id, session_id, work_item_id, status, updated_at) => ({
              id, session_id, work_item_id, status, updated_at, created_at: updated_at,
            });
            const selected = selectCurrentWorkbenchRuns([
              run('old-failure', 'session-old', 'work-1', 'failed', 100),
              run('new-success', 'session-new', 'work-1', 'completed', 300),
              run('old-session-failure', 'session-free', null, 'failed', 120),
              run('new-session-run', 'session-free', null, 'running', 250),
              run('unlinked-failure', 'session-other', null, 'failed', 200),
            ]);
            const ids = selected.map((value) => value.id);
            if (ids.includes('old-failure') || ids.includes('old-session-failure')) process.exit(11);
            if (!ids.includes('new-success') || !ids.includes('new-session-run') || !ids.includes('unlinked-failure')) process.exit(12);

            const current = {
              actionItems: [{ id: 'last-action' }], unassignedItems: [], summary: null,
              computedAt: null, runs: [], actionSource: null, runSource: null,
              actionUpdatedAt: null, runUpdatedAt: null,
            };
            const rejectedActions = { status: 'rejected', reason: new Error('actions failed') };
            const liveRuns = { status: 'fulfilled', value: { value: { runs: [run('run-1', 's-1', null, 'running', 1)] }, source: 'live', updatedAt: 200 } };
            const firstMerge = mergeWorkbenchDomains(current, rejectedActions, liveRuns);
            if (firstMerge.actionUpdatedAt !== null || firstMerge.actionItems[0].id !== 'last-action') process.exit(21);
            if (firstMerge.runUpdatedAt !== 200 || firstMerge.runSource !== 'live') process.exit(22);

            const cachedActions = { status: 'fulfilled', value: { value: {
              items: [{ id: 'fresh-action' }], unassigned: [], summary: {}, computed_at: 10,
            }, source: 'cache', updatedAt: 100 } };
            const secondMerge = mergeWorkbenchDomains(firstMerge, cachedActions, { status: 'rejected', reason: new Error('runs failed') });
            if (secondMerge.actionUpdatedAt !== 100 || secondMerge.actionSource !== 'cache') process.exit(31);
            if (secondMerge.runUpdatedAt !== 200 || secondMerge.runs[0].id !== 'run-1') process.exit(32);
            """
        )
        result = subprocess.run(
            ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_desktop_home_uses_connectivity_state_and_neutral_visible_focus(self) -> None:
        home = (ROOT / "src/views/HomeView.tsx").read_text(encoding="utf-8")
        channels = (ROOT / "src/lib/channels.ts").read_text(encoding="utf-8")
        store = (ROOT / "src/stores/workbenchStore.ts").read_text(encoding="utf-8")
        css = (ROOT / "src/styles/app.css").read_text(encoding="utf-8")
        self.assertIn("const server = useConnectivityStore", home)
        self.assertIn("const localAgent = useConnectivityStore", home)
        self.assertIn("refreshConnectivity", home)
        self.assertNotIn("useWorkbenchStore", home)
        self.assertNotIn("actionUpdatedAt", home)
        self.assertNotIn("runUpdatedAt", home)
        self.assertNotIn("event.key === 'Tab'", home)
        self.assertNotIn(".home-quick-start.is-keyboard-navigation .composer:focus-within", css)
        self.assertIn(":focus-visible", css)
        self.assertEqual(2, channels.count("options.onResolvedState?.(channelSnapshot().server)"))
        self.assertIn("api.listPersonalActionItems(localDate(), { onResolvedState })", store)
        self.assertIn("api.listRuns(undefined, { onResolvedState })", store)
        self.assertNotIn("const server = channelSnapshot().server", store)


if __name__ == "__main__":
    unittest.main()
