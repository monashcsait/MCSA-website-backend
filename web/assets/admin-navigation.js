/* Navigation only: reuse the CMS buttons without changing forms or permissions. */
(() => {
  'use strict';
  const root = document.querySelector('#admin-root');
  if (!root || typeof HTMLDialogElement === 'undefined') return;
  const mobile = window.matchMedia('(max-width: 760px), (min-width: 761px) and (max-width: 900px) and (max-height: 500px)');
  let activeDialog = null;

  function closeActive() {
    if (activeDialog?.open) activeDialog.close();
    activeDialog = null;
    document.body.classList.remove('cms-menu-open');
  }

  function enhance() {
    closeActive();
    const cms = root.querySelector('.cms');
    const layout = cms?.querySelector('.cms-layout');
    const tabs = layout?.querySelector('.cms-tabs');
    if (!tabs || cms.classList.contains('cms-mobile-navigation')) return;
    const buttons = [...tabs.querySelectorAll('[data-section]')];
    if (!buttons.length) return;

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'cms-menu-toggle';
    toggle.setAttribute('aria-haspopup', 'dialog');
    toggle.setAttribute('aria-controls', 'cms-menu-drawer');
    toggle.setAttribute('aria-expanded', 'false');
    const selected = tabs.querySelector('.selected') || buttons[0];
    toggle.textContent = `☰ 栏目 · ${selected.textContent.trim()}`;

    const dialog = document.createElement('dialog');
    dialog.id = 'cms-menu-drawer';
    dialog.className = 'cms-menu-drawer';
    dialog.setAttribute('aria-labelledby', 'cms-menu-title');
    dialog.innerHTML = '<div class="cms-menu-heading"><strong id="cms-menu-title">管理栏目</strong><button type="button" class="cms-menu-close" autofocus>关闭菜单 ×</button></div><nav class="cms-menu-items" aria-label="管理栏目"></nav><p class="cms-menu-help">选择栏目后返回编辑</p>';
    const items = dialog.querySelector('.cms-menu-items');
    buttons.forEach(original => {
      const item = original.cloneNode(true);
      item.removeAttribute('id');
      item.type = 'button';
      item.removeAttribute('aria-pressed');
      if (original === selected) item.setAttribute('aria-current', 'true');
      else item.removeAttribute('aria-current');
      item.addEventListener('click', () => {
        closeActive();
        original.click();
        // The existing handler renders a new editor; focus its title, not an old button.
        const title = root.querySelector('.cms-editor > h2');
        if (title) {
          title.tabIndex = -1;
          title.focus();
        }
      });
      items.append(item);
    });
    toggle.addEventListener('click', () => {
      if (!mobile.matches || layout.inert) return;
      activeDialog = dialog;
      dialog.showModal();
      toggle.setAttribute('aria-expanded', 'true');
      document.body.classList.add('cms-menu-open');
    });
    dialog.querySelector('.cms-menu-close').addEventListener('click', closeActive);
    dialog.addEventListener('close', () => {
      // A queued close event from an old render must not unlock a newer dialog.
      if (!activeDialog || activeDialog === dialog) {
        document.body.classList.remove('cms-menu-open');
        activeDialog = null;
      }
      toggle.setAttribute('aria-expanded', 'false');
    });
    dialog.addEventListener('cancel', event => {
      event.preventDefault();
      closeActive();
    });
    dialog.addEventListener('keydown', event => {
      if (event.key !== 'Tab') return;
      const focusable = [...dialog.querySelectorAll('button:not(:disabled)')];
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const bounds = dialog.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) closeActive();
    });
    layout.prepend(toggle);
    cms.append(dialog);
    // Hide the old strip only after enhancement is available; it remains the fallback.
    cms.classList.add('cms-mobile-navigation');
  }

  new MutationObserver(enhance).observe(root, { childList: true });
  mobile.addEventListener('change', closeActive);
  enhance();
})();
