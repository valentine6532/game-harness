// Locate a working Python 3 without depending on Windows Store execution aliases.
// Node is already used by both supported coding-agent CLIs.
import { spawnSync } from 'node:child_process';
import { existsSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const directory = dirname(fileURLToPath(import.meta.url));
const mode = process.argv[2];
if (!['lifecycle', 'guard'].includes(mode)) {
  process.stderr.write('[game-harness] Invalid hook mode\n');
  process.exit(1);
}
const input = await new Promise((resolve, reject) => {
  let data = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => { data += chunk; });
  process.stdin.on('end', () => resolve(data));
  process.stdin.on('error', reject);
});
const candidates = [];
if (process.env.GAME_HARNESS_PYTHON) candidates.push([process.env.GAME_HARNESS_PYTHON]);
if (process.platform === 'win32') {
  const pythonRoot = join(process.env.LOCALAPPDATA || join(homedir(), 'AppData', 'Local'), 'Programs', 'Python');
  if (existsSync(pythonRoot)) {
    for (const name of readdirSync(pythonRoot).filter((name) => /^Python3\d+$/.test(name)).sort().reverse()) {
      candidates.push([join(pythonRoot, name, 'python.exe')]);
    }
  }
  candidates.push(['py', '-3']);
}
candidates.push(['python3'], ['python']);
for (const [executable, ...prefix] of candidates) {
  const check = spawnSync(executable, [...prefix, '-c', 'import sys; print(sys.version_info >= (3, 10))'],
    { encoding: 'utf8', timeout: 3000, windowsHide: true });
  if (check.status !== 0 || check.stdout?.trim() !== 'True') continue;
  const script = join(directory, mode === 'guard' ? 'work_guard.py' : 'global_runtime.py');
  const args = [...prefix, script, ...(mode === 'lifecycle' ? ['hook'] : [])];
  const result = spawnSync(executable, args, { input, encoding: 'utf8', windowsHide: true,
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' }, maxBuffer: 8 * 1024 * 1024 });
  if (result.stdout) process.stdout.write(result.stdout);
  if (result.stderr) process.stderr.write(result.stderr);
  if (result.error) process.stderr.write(`[game-harness] ${result.error.message}\n`);
  process.exit(mode === 'guard' && result.status !== 0 ? 2 : (result.status ?? 1));
}
process.stderr.write('[game-harness] Python 3.10+ is required; set GAME_HARNESS_PYTHON to its executable.\n');
process.exit(mode === 'guard' ? 2 : 1);
