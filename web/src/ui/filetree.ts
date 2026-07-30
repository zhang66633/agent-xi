/**
 * 文件树面板 — 左侧可折叠项目文件浏览器
 *
 * 点击文件: 发送 "请读取 <path>" 到输入框
 * 右键: 复制文件路径
 */
import { API_BASE } from '../config';

interface TreeNode {
  name: string;
  path: string;
  isDir: boolean;
  children?: TreeNode[];
}

export class FileTree {
  private container: HTMLElement;
  private panel: HTMLElement;
  private visible = false;
  private onSelectPath: ((path: string) => void) | null = null;

  constructor() {
    this.container = document.getElementById('filetree-container')!;
    this.panel = document.getElementById('filetree-panel')!;
    this._bindNav();
  }

  /** 设置文件选中回调（填充到输入框） */
  onSelect(handler: (path: string) => void): void {
    this.onSelectPath = handler;
  }

  /** 切换显隐 */
  toggle(): void {
    this.visible = !this.visible;
    const roster = document.getElementById('roster-panel');
    if (this.visible) {
      if (roster) roster.hidden = true;
      this.panel.hidden = false;
      this.load();
    } else {
      if (roster) roster.hidden = false;
      this.panel.hidden = true;
    }
  }

  get isVisible(): boolean {
    return this.visible;
  }

  /** 加载项目文件树 */
  async load(): Promise<void> {
    this.container.innerHTML = '<div class="ft-loading">加载文件树...</div>';

    try {
      const res = await fetch(`${API_BASE}/api/files/tree`);
      const data = await res.json() as { ok: boolean; tree?: TreeNode; error?: string };
      if (!data.ok || !data.tree) {
        this.container.innerHTML = `<div class="ft-error">${data.error || '加载失败'}</div>`;
        return;
      }
      this.render(data.tree);
    } catch {
      // fallback: 用静态目录模拟
      this.render(this._fallbackTree());
    }
  }

  /** 渲染树 */
  render(node: TreeNode): void {
    const root = document.createElement('div');
    root.className = 'ft-root';
    this._buildNode(root, node, 0);
    this.container.innerHTML = '';
    this.container.appendChild(root);
  }

  private _buildNode(parent: HTMLElement, node: TreeNode, depth: number): void {
    const row = document.createElement('div');
    row.className = 'ft-row';
    row.style.paddingLeft = `${depth * 16 + 4}px`;

    const icon = document.createElement('span');
    icon.className = node.isDir ? 'ft-icon ft-dir' : 'ft-icon ft-file';

    const name = document.createElement('span');
    name.className = 'ft-name';
    name.textContent = node.name;
    name.title = node.path;

    if (!node.isDir) {
      name.addEventListener('click', () => {
        this.onSelectPath?.(node.path);
      });

      // 右键复制路径
      name.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        navigator.clipboard.writeText(node.path).catch(() => {});
      });
    }

    row.appendChild(icon);
    row.appendChild(name);

    if (node.isDir && node.children) {
      row.addEventListener('click', (e) => {
        e.stopPropagation();
        const children = row.nextElementSibling as HTMLElement | null;
        if (children?.classList.contains('ft-children')) {
          const isOpen = children.style.display !== 'none';
          children.style.display = isOpen ? 'none' : 'block';
          icon.textContent = isOpen ? '▸' : '▾';
        }
      });
      icon.textContent = '▾';
    } else if (node.isDir) {
      icon.textContent = '▸';
    }

    parent.appendChild(row);

    if (node.isDir && node.children && node.children.length > 0) {
      const childrenWrap = document.createElement('div');
      childrenWrap.className = 'ft-children';
      for (const child of node.children) {
        this._buildNode(childrenWrap, child, depth + 1);
      }
      parent.appendChild(childrenWrap);
    }
  }

  /** Fallback: 通过后端 API 获取的简化树，API 不可用时用静态模拟 */
  private _fallbackTree(): TreeNode {
    return {
      name: 'agent_xi_project',
      path: '.',
      isDir: true,
      children: [
        {
          name: 'src', path: 'src', isDir: true, children: [
            { name: 'agent_xi', path: 'src/agent_xi', isDir: true, children: [
              { name: 'brain', path: 'src/agent_xi/brain', isDir: true, children: [] },
              { name: 'tools', path: 'src/agent_xi/tools', isDir: true, children: [] },
              { name: 'llm', path: 'src/agent_xi/llm', isDir: true, children: [] },
              { name: 'server', path: 'src/agent_xi/server', isDir: true, children: [] },
              { name: 'memory', path: 'src/agent_xi/memory', isDir: true, children: [] },
              { name: 'agents', path: 'src/agent_xi/agents', isDir: true, children: [] },
              { name: 'loop', path: 'src/agent_xi/loop', isDir: true, children: [] },
              { name: 'scheduler', path: 'src/agent_xi/scheduler', isDir: true, children: [] },
              { name: 'mcp', path: 'src/agent_xi/mcp', isDir: true, children: [] },
              { name: 'skills', path: 'src/agent_xi/skills', isDir: true, children: [] },
              { name: 'cli', path: 'src/agent_xi/cli', isDir: true, children: [] },
              { name: '__init__.py', path: 'src/agent_xi/__init__.py', isDir: false },
              { name: '__main__.py', path: 'src/agent_xi/__main__.py', isDir: false },
              { name: 'config.py', path: 'src/agent_xi/config.py', isDir: false },
            ]},
          ],
        },
        {
          name: 'web', path: 'web', isDir: true, children: [
            { name: 'index.html', path: 'web/index.html', isDir: false },
            { name: 'src', path: 'web/src', isDir: true, children: [] },
          ],
        },
        {
          name: 'config', path: 'config', isDir: true, children: [
            { name: 'default.yaml', path: 'config/default.yaml', isDir: false },
            { name: 'identity.md', path: 'config/identity.md', isDir: false },
            { name: 'personality.md', path: 'config/personality.md', isDir: false },
            { name: 'loop.md', path: 'config/loop.md', isDir: false },
            { name: 'agents.md', path: 'config/agents.md', isDir: false },
          ],
        },
        {
          name: 'tests', path: 'tests', isDir: true, children: [
            { name: 'conftest.py', path: 'tests/conftest.py', isDir: false },
            { name: 'test_brain.py', path: 'tests/test_brain.py', isDir: false },
            { name: 'test_server.py', path: 'tests/test_server.py', isDir: false },
            { name: 'test_memory.py', path: 'tests/test_memory.py', isDir: false },
          ],
        },
        { name: 'README.md', path: 'README.md', isDir: false },
        { name: 'pyproject.toml', path: 'pyproject.toml', isDir: false },
        { name: 'Dockerfile', path: 'Dockerfile', isDir: false },
        { name: '.env.example', path: '.env.example', isDir: false },
        { name: 'start.bat', path: 'start.bat', isDir: false },
      ],
    };
  }

  private _bindNav(): void {
    const navBtn = document.getElementById('nav-filetree');
    if (navBtn) {
      navBtn.addEventListener('click', () => this.toggle());
    }
  }
}
