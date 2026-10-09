// Reuse the upstream behavior suite against the exact Android source transform.
import { readFile, writeFile, unlink } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const suiteURL = new URL('tests/.android-widget.generated.test.mjs', import.meta.url);
const source = await readFile(new URL('tests/widget.test.mjs', import.meta.url), 'utf8');
const transformed = source.replaceAll('pua_screen', 'android_screen')
  .replaceAll('截图已复制到剪贴板','截图已刷新')
  .replace('for (let i = 0; i < 5; i++) await h.tick();','for (let i = 0; i < 38; i++) await h.tick();')
  .replace('for (let i = 0; i < 4; i++) await h.tick();','for (let i = 0; i < 31; i++) await h.tick();')
  .replace("const source = await readFile(new URL('../src/app.ts', import.meta.url), 'utf8');",
    "const { adapt } = await import('../adapt.android.mjs');\nconst source = adapt(await readFile(new URL('../src/app.ts', import.meta.url), 'utf8'));")
  .replace('].delay, 250)', '].delay, 33)');
try {
  await writeFile(suiteURL, transformed);
  const result = spawnSync(process.execPath, ['--test', fileURLToPath(suiteURL)], { stdio: 'inherit' });
  process.exitCode = result.status ?? 1;
} finally { await unlink(suiteURL); }
