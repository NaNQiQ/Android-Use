import { build } from 'esbuild';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { adapt } from './adapt.android.mjs';
const here = new URL('./', import.meta.url);
const source = adapt(await readFile(new URL('src/app.ts', here), 'utf8'));
const result = await build({
  stdin: { contents: source, loader: 'ts', resolveDir: fileURLToPath(here) },
  bundle: true, platform: 'browser', target: 'es2022', format: 'esm', minify: true,
  pure: ['console.debug'], write: false, legalComments: 'inline',
});
const html = adapt(await readFile(new URL('index.html', here), 'utf8'));
const css = await readFile(new URL('style.css', here), 'utf8');
const widget = html.replace('/*__STYLE__*/', () => css + '.dynamic-island{display:none}.receiver{display:none}')
  .replace('/*__SCRIPT__*/', () => result.outputFiles[0].text.replace(/<\/script/gi, '<\\/script'));
await mkdir(new URL('../assets/', here), { recursive: true });
await writeFile(new URL('../assets/android-screen.html', here), widget);
console.log('Built Android screen widget from upstream editable UI source.');
