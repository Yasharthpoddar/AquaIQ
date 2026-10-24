import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { transformWithOxc } from 'vite';

const require = createRequire(import.meta.url);
const modules = new Map();

// Execute the actual JSX components in the existing Node/SSR test runtime.
// Only CSS side-effect imports are omitted; no rendered component is stubbed.
async function moduleUrl(url) {
  const key = url.href;
  if (!modules.has(key)) modules.set(key, (async () => {
    const source = readFileSync(url, 'utf8').replace(/^import\s+['"][^'"]+\.css['"];?\s*$/gm, '');
    let { code } = await transformWithOxc(source, url.pathname, { jsx: { runtime: 'automatic' } });
    const imports = [...code.matchAll(/from (["'])([^"']+)\1/g)];
    for (const match of imports.reverse()) {
      const specifier = match[2];
      let target;
      if (specifier.startsWith('.')) {
        const resolved = new URL(specifier, url);
        // Existing app imports omit both JS and JSX extensions.
        if (!/\.[a-z]+$/i.test(resolved.pathname)) {
          try { readFileSync(new URL(resolved.href + '.js')); resolved.pathname += '.js'; }
          catch { resolved.pathname += '.jsx'; }
        }
        target = resolved.pathname.endsWith('.jsx') ? await moduleUrl(resolved) : resolved.href;
      } else {
        target = pathToFileURL(require.resolve(specifier)).href;
      }
      code = code.slice(0, match.index) + `from ${JSON.stringify(target)}` + code.slice(match.index + match[0].length);
    }
    return `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`;
  })());
  return modules.get(key);
}

export async function loadJsx(url) {
  return import(await moduleUrl(url instanceof URL ? url : new URL(url, import.meta.url)));
}
