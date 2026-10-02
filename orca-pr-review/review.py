#!/usr/bin/env python3
"""Parallel PR reviews in the current Orca workspace, without orchestration."""
import argparse
import concurrent.futures
import datetime
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid

from runtime import LocalRuntime, RpcError

DEFAULT_CONFIG = Path.home() / '.config/orca-pr-review/config.json'
VERDICT = re.compile(r'^\s*(?:#{1,6}\s+)?(?:\*\*)?Merge verdict:(?:\*\*)?\s*(?:\*\*)?(YES|NO|UNCERTAIN)\s*(?:\*\*)?\s*$', re.I)


def configured_agents(explicit, config_path):
    if explicit is not None:
        agents = [a.strip() for a in explicit.split(',')]
    else:
        try:
            agents = json.loads(config_path.read_text()).get('agents')
        except FileNotFoundError:
            raise RuntimeError(f'No reviewer config at {config_path}; use --agents.') from None
    if (not isinstance(agents, list) or not 1 <= len(agents) <= 16
            or any(not isinstance(a, str) or not re.fullmatch(r'[a-z][a-z0-9-]*', a) for a in agents)
            or len(set(agents)) != len(agents)):
        raise RuntimeError('Configure 1–16 distinct Orca agent IDs, not executable paths.')
    return agents


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def command(argv, cwd=None):
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f'{shlex.join(argv[:4])}: {(result.stderr or result.stdout).strip()}')
    return result.stdout.strip()


def worker_spec(meta, agent, report):
    return f'''Review PR #{meta['number']}: {meta['url']}
Do a code review and explain whether it can be merged, including any blocking issues.
Do not change source code, switch branches, or merge/post anything.
Write your finished review to {report} (temporary file, then rename).
End the report with Merge verdict: YES, NO, or UNCERTAIN (choose one).
'''


def read_report(path, meta=None, agent=None):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError('report must be a regular non-symlink file under 2 MB')
    with path.open('rb') as stream:
        snapshot = stream.read(2_000_001)
    if len(snapshot) > 2_000_000:
        raise ValueError('report exceeds 2 MB')
    text = snapshot.decode('utf-8')
    if path.suffix == '.json':
        # Offline collection of earlier runs remains possible; never restart their workers.
        report = json.loads(text)
        if any(report.get(k) != v for k, v in [('agent', agent), ('head', meta['headRefOid']), ('base', meta['baseRefOid'])]):
            raise ValueError('legacy report identity/commit mismatch')
        return {'markdown': report['summary'] + '\n\n````json\n' + json.dumps(report, indent=2) + '\n````',
                'verdict': 'UNCERTAIN', '_snapshot': snapshot}
    lines = text.strip().splitlines()
    verdict = VERDICT.fullmatch(lines[-1]) if lines else None
    if not verdict:
        raise ValueError('finished report must end with Merge verdict: YES/NO/UNCERTAIN')
    if not any(line.strip() for line in lines[:-1]):
        raise ValueError('report must contain a review, not just a verdict')
    return {'markdown': text, 'verdict': verdict[1].upper(), '_snapshot': snapshot}


def consolidate(state, directory):
    meta = state['pr']
    lines = [f"# PR #{meta['number']} — parallel review", '', meta['url'], '',
             '## Reviewer status', '']
    reports = {}
    for agent, worker in state['workers'].items():
        status = worker['status']
        if status == 'succeeded':
            try:
                extension = '.json' if state.get('reportFormat') != 'markdown' else '.md'
                reports[agent] = read_report(directory / f'{agent}{extension}', meta, agent)
            except (OSError, ValueError, TypeError, KeyError) as error:
                status = f'invalid/missing report: {error}'
                worker['status'] = 'report invalid or missing'
                worker['reportError'] = str(error)
                worker.pop('verdict', None)
        lines.append(f'- **{agent}**: {status}')
        if worker.get('error'):
            lines.append(f"  - {worker['error']}")
        if worker.get('launchReceipt', {}).get('warning'):
            lines.append(f"  - {worker['launchReceipt']['warning']}")
    votes = [r['verdict'] for r in reports.values()]
    overall = ('NO' if 'NO' in votes else 'YES' if len(votes) == len(state['workers'])
               and votes and all(v == 'YES' for v in votes) else 'UNCERTAIN')
    lines += ['', '## Merge recommendation', '', f'**{overall}**', '',
              'Reviewer recommendations only—not merge authorization or verified CI status.', '']
    for agent, report in reports.items():
        lines.append(f"- **{agent}**: {report['verdict']}")
    lines += ['', '## Individual reviews', '']
    for agent, report in reports.items():
        lines += [f'### {agent}', '', report['markdown'], '']
    evidence = ('Agent sessions remain open in the existing workspace. No orchestration preamble, '
                'hooks, status polling, or automatic terminal closing is used.'
                if state.get('launchMode') == 'direct-v1' else
                'Legacy orchestration run: collected offline; no workers were restarted or changed.')
    lines += ['## Run evidence', '', f"Manifest: `{directory / 'manifest.json'}`", '',
              evidence + ' Prompt restrictions are not an OS sandbox.', '']
    destination = directory / f"pr-{meta['number']}-review.md"
    temporary = destination.with_suffix('.md.tmp')
    temporary.write_text('\n'.join(lines))
    temporary.replace(destination)
    return destination


def launch_one(runtime, worker, replay=False):
    # The whole prompt is part of ONE launch, never a later terminal.send or dispatch.
    receipt = runtime.call('agent.launchReplay' if replay else 'agent.launch', worker['launchParams'])
    if not isinstance(receipt, dict) or receipt.get('outcome', {}).get('kind') not in ('terminal', 'structured'):
        raise RuntimeError('Launch returned an invalid surface receipt; outcome unknown.')
    delivery = receipt.get('prompt', {}).get('outcome')
    if delivery not in ('handed-to-terminal', 'journaled', 'not-delivered'):
        raise RuntimeError('Launch returned an unknown prompt receipt; do not relaunch blindly.')
    return receipt


def launch_wave(runtime, state, directory, agents, replay=False):
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(agents)) as pool:
        futures = {pool.submit(launch_one, runtime, state['workers'][a], replay): a for a in agents}
        for future in concurrent.futures.as_completed(futures):
            agent = futures[future]
            worker = state['workers'][agent]
            try:
                receipt = future.result()
                worker['launchReceipt'] = receipt
                worker.pop('error', None)
                worker['status'] = ('running' if receipt['prompt']['outcome'] != 'not-delivered'
                                    else 'prompt not delivered; session retained')
            except Exception as error:
                worker['status'] = 'launch outcome unknown'
                worker['error'] = str(error)
                if isinstance(error, RpcError):
                    worker['errorReceipt'] = error.receipt
            print(f'{agent}: {worker["status"]}', flush=True)
            if worker.get('error'):
                print('  ' + worker['error'], file=sys.stderr)
            atomic_json(directory / 'manifest.json', state)


def wait_for_reviews(state, directory, minutes, collect_only=False):
    deadline = time.monotonic() + minutes * 60
    previous = {}
    observations = 0
    while True:
        observations += 1
        # Files are evidence even when a launch receipt was lost or a wait expired.
        for agent, worker in state['workers'].items():
            extension = '.md' if state.get('reportFormat') == 'markdown' else '.json'
            path = directory / f'{agent}{extension}'
            try:
                report = read_report(path, state['pr'], agent)
                snapshot = report['_snapshot']
                if previous.get(agent) == snapshot:
                    changed = worker['status'] != 'succeeded'
                    worker['status'] = 'succeeded'
                    worker['verdict'] = report['verdict']
                    worker.pop('reportError', None)
                    worker.pop('error', None)
                    if changed:
                        print(f'{agent}: review received — {report["verdict"]}', flush=True)
                else:
                    previous[agent] = snapshot
                    if worker['status'] == 'succeeded':
                        worker['status'] = 'report awaiting confirmation'
            except (OSError, ValueError, TypeError, KeyError) as error:
                previous.pop(agent, None)
                worker['reportError'] = str(error)
                if worker['status'] == 'succeeded':
                    worker['status'] = 'report invalid or missing'
                    worker.pop('verdict', None)
        atomic_json(directory / 'manifest.json', state)
        consolidate(state, directory)
        pending = [w for w in state['workers'].values() if w['status'] == 'running']
        if observations >= 2 and (collect_only or not pending):
            return
        if not collect_only and observations >= 2 and time.monotonic() >= deadline:
            for worker in pending:
                worker['status'] = 'wait timed out; session retained'
                if worker.get('reportError'):
                    worker['error'] = worker['reportError']
            atomic_json(directory / 'manifest.json', state)
            consolidate(state, directory)
            return
        time.sleep(1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pr', nargs='?', type=int)
    parser.add_argument('--repo', type=Path, default=Path.cwd(), help='Existing local Orca workspace path')
    parser.add_argument('--remote', default='origin')
    parser.add_argument('--agents', help='Comma-separated Orca agent IDs; overrides config')
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--timeout', type=float, default=30, help='Minutes to wait for report files; never kills agents')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--resume', type=Path)
    parser.add_argument('--collect-only', type=Path)
    parser.add_argument('--doctor', action='store_true')
    # Accepted for old Quick Commands; not used to launch or bind orchestration anymore.
    parser.add_argument('--orca', help=argparse.SUPPRESS)
    parser.add_argument('--terminal', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    state = directory = None
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise RuntimeError('--timeout must be finite and positive')
        if args.collect_only:
            directory = args.collect_only.expanduser().resolve()
            state = json.loads((directory / 'manifest.json').read_text())
            wait_for_reviews(state, directory, args.timeout, collect_only=True)
            print(consolidate(state, directory))
            atomic_json(directory / 'manifest.json', state)
            return 0 if state['workers'] and all(w['status'] == 'succeeded' for w in state['workers'].values()) else 2
        if args.doctor:
            runtime = LocalRuntime()
            runtime.preflight()
            print('Configured reviewers: ' + ', '.join(configured_agents(args.agents, args.config.expanduser())))
            print('Authenticated local Orca agent.launch and replay APIs available. No agents started.')
            return 0
        if args.resume:
            directory = args.resume.expanduser().resolve()
            state = json.loads((directory / 'manifest.json').read_text())
            if state.get('launchMode') != 'direct-v1':
                raise RuntimeError('This is an old orchestration run. Use --collect-only; do not relaunch its workers.')
            # First recover reports without needing a running Orca or a launch receipt.
            wait_for_reviews(state, directory, args.timeout, collect_only=True)
            unknown = [a for a, w in state['workers'].items() if w['status'] in ('starting', 'launch outcome unknown')]
            if unknown:
                try:
                    runtime = LocalRuntime()
                    runtime.preflight()
                    if state['runtimeId'] != runtime.metadata['runtimeId']:
                        raise RuntimeError('Orca restarted; launch replay skipped. Report collection remains available.')
                except Exception as error:
                    print(f'Launch recovery skipped: {error}', file=sys.stderr)
                else:
                    launch_wave(runtime, state, directory, unknown, replay=True)
            for worker in state['workers'].values():
                if worker['status'].startswith('wait timed out'):
                    worker['status'] = 'running'
                    worker.pop('error', None)
        else:
            runtime = LocalRuntime()
            runtime.preflight()
            agents = configured_agents(args.agents, args.config.expanduser())
            if args.pr is None:
                args.pr = int(input('PR number: ').strip().removeprefix('#'))
            if args.pr <= 0:
                raise RuntimeError('PR number must be positive')
            for tool in ('git', 'gh'):
                if not shutil.which(tool):
                    raise RuntimeError(f'Missing executable: {tool}')
            repo = Path(command(['git', '-C', str(args.repo.expanduser()), 'rev-parse', '--show-toplevel'])).resolve()
            workspace = runtime.call('worktree.show', {'worktree': f'path:{repo}'})['worktree']
            if workspace.get('hostId', 'local') != 'local':
                raise RuntimeError('Only native local workspaces are supported, not SSH/WSL/remote hosts.')
            if not workspace.get('id'):
                raise RuntimeError('Orca did not identify an existing workspace')
            remote_url = command(['git', 'remote', 'get-url', args.remote], repo)
            owner = json.loads(command(['gh', 'repo', 'view', remote_url, '--json', 'nameWithOwner'], repo))['nameWithOwner']
            meta = json.loads(command(['gh', 'pr', 'view', str(args.pr), '--repo', owner,
                                      '--json', 'number,url,headRefOid,baseRefOid'], repo))
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            token = uuid.uuid4().hex[:8]
            directory = (args.output_dir or Path.home() / '.local/share/orca-pr-review/reports' /
                         owner.replace('/', '--') / f'pr-{args.pr}-{stamp}-{token}').expanduser().resolve()
            directory.mkdir(parents=True, exist_ok=False)
            directory.chmod(0o700)
            state = {'launchMode': 'direct-v1', 'reportFormat': 'markdown', 'pr': meta, 'repo': str(repo),
                     'runtimeId': runtime.metadata['runtimeId'], 'worktreeId': workspace['id'], 'workers': {}}
            for agent in agents:
                state['workers'][agent] = {'status': 'starting', 'launchParams': {
                    'agent': agent, 'operationId': f'{int(time.time() * 1000)}-{uuid.uuid4().hex}',
                    'target': {'kind': 'existing', 'worktree': f'id:{workspace["id"]}'},
                    'prompt': {'text': worker_spec(meta, agent, directory / f'{agent}.md'), 'delivery': 'submit'}}}
            # Persist identities and exact launch requests BEFORE any concurrent mutation.
            atomic_json(directory / 'manifest.json', state)
            print(f'\nReport folder (shared by all reviewers):\n{directory}', flush=True)
            for agent in agents:
                print(f'  {agent}: {directory / f"{agent}.md"}', flush=True)
            print(f'\nCollect later:\n  orca-pr-review --collect-only {shlex.quote(str(directory))}\n', flush=True)
            launch_wave(runtime, state, directory, agents)
        wait_for_reviews(state, directory, args.timeout)
        print(consolidate(state, directory))
        atomic_json(directory / 'manifest.json', state)
        return 0 if state['workers'] and all(w['status'] == 'succeeded' for w in state['workers'].values()) else 2
    except (Exception, KeyboardInterrupt) as error:
        print(f'Review interrupted or blocked: {error or "Ctrl-C"}', file=sys.stderr)
        if directory and state:
            atomic_json(directory / 'manifest.json', state)
            print(consolidate(state, directory), file=sys.stderr)
            print('Agent sessions were not killed or closed. Resume using this report directory.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
