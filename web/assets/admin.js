/* Chinese-only CMS. All changes stay in memory until Save is confirmed by the server. */
(() => {
  'use strict';
  const {
    esc,
    image
  } = window.MCSA;
  let state, revision, csrf, dirty = false;
  let section = 'posts';
  const root = () => document.querySelector('#admin-root');
  const names = {
    posts: '活动与文章',
    pages: '页面文字',
    departments: '部门与招新链接',
    team: '现任主席团',
    terms: '历任主席团',
    merchants: '折扣商家',
    regions: '商家地区',
    categories: '商家种类',
    sponsors: '年度赞助',
    socials: '联系与社交媒体',
    footerLinks: '底部链接',
    settings: '网站设置',
    layout: '配色与布局',
    homeSections: '首页区块排序',
    interfaceText: '按钮与界面文字'
  };
  const fieldNames = {
    title: '标题',
    text: '正文',
    name: '名称',
    intro: '部门介绍',
    recruitment: '招新说明',
    role: '职位',
    description: '介绍',
    url: '超链接（留空则不跳转）',
    image: '图片',
    account: '账号原文',
    date: '发布日期',
    published: '发布到网站',
    year: '排序年份（越大越靠前）',
    logo: '左上角标志与网站图标',
    heroLogo: '首页大标志',
    opening: '开场动画',
    openingDuration: '开场时长（毫秒）',
    footer: '版权文字',
    email: '联系邮箱',
    heroBlurb: '首页标志下方文字',
    keywords: '标签（用竖线 ｜ 分隔）',
    departmentOverview: '部门区默认总介绍',
    departmentOverviewTitle: '部门区默认标题',
    departmentOverviewTags: '默认标签（用竖线 ｜ 分隔）',
    departmentHint: '部门标题下的说明',
    departmentButton: '部门详情按钮模板（{name} 自动替换为部门名称）',
    departmentReset: '旧版概览文字（新版前台不使用）',
    contentWidth: '内容最大宽度（960—1600像素）',
    baseFontSize: '正文基础字号（14—20像素）',
    sectionSpacing: '区块上下留白（30—110像素）',
    cardRadius: '主要卡片圆角（12—48像素）',
    primaryColor: '主题红色',
    backgroundColor: '背景渐变浅色',
    heroCardWidth: '首页白卡宽度（300—520像素）',
    heroSlope: '红色背景斜切位置（15—80）',
    presidentImageShare: '主席团照片宽度占比（35—55）',
    presidentHeight: '主席团桌面卡片高度（420—680像素）',
    departmentHeight: '部门列表桌面高度（360—680像素）',
    departmentSpeed: '部门滚动速度（5—50像素/秒）',
    contactQrSize: '二维码框尺寸（80—160像素）',
    contactColumns: '电脑端二维码列数（2—4）',
    carouselSeconds: '主席团轮播间隔（4—20秒）',
    departmentDirection: '部门自动滚动方向',
    departmentAutoplay: '启用部门自动滚动'

  };
  const tri = () => ({
    zh: '',
    en: '',
    hant: ''
  });
  const uid = () => 'item-' + crypto.randomUUID();
  const templates = {
    posts: () => ({
      id: uid(),
      page: 'latest-events',
      title: tri(),
      text: tri(),
      image: '',
      url: '',
      published: false,
      date: new Date().toISOString().slice(0, 10),
      crop: null
    }),
    departments: () => ({
      id: uid(),
      name: tri(),
      intro: tri(),
      recruitment: tri(),
      keywords: tri(),
      image: '',
      url: ''
    }),
    team: () => ({
      name: tri(),
      role: tri(),
      description: tri(),
      image: '',
      url: '',
      tags: []
    }),
    terms: () => ({
      id: uid(),
      name: tri(),
      year: new Date().getFullYear() - 1,
      members: []
    }),
    member: () => ({
      name: tri(),
      role: tri(),
      image: '',
      url: ''
    }),
    merchants: () => ({
      id: uid(),
      name: tri(),
      text: tri(),
      image: '',
      url: '',
      region: state.regions[0]?.id || '',
      category: state.categories[0]?.id || ''
    }),
    sponsors: () => ({
      id: uid(),
      name: tri(),
      image: '',
      url: ''
    }),
    socials: () => ({
      id: uid(),
      name: tri(),
      account: '',
      placement: 'qr',
      image: '',
      url: '',
      crop: null
    }),
    footerLinks: () => ({
      id: uid(),
      name: tri(),
      url: ''
    }),
    regions: () => ({
      id: uid(),
      name: tri()
    }),
    categories: () => ({
      id: uid(),
      name: tri()
    })
  };

  async function api(path, options = {}) {
    const headers = {
      ...options.headers
    };
    if (!(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
    if (csrf) headers['X-CSRF-Token'] = csrf;
    const response = await fetch('/api' + path, {
      ...options,
      headers
    });
    let result;
    try {
      result = await response.json();
    } catch {
      throw Error('请通过启动脚本打开后台，不能直接双击后台网页。');
    }
    if (!response.ok) {
      const errors = {
        invalid_login: '账号或密码不正确。',
        revision_conflict: '其他管理员已经更新内容。请先复制未保存文字，再刷新页面重新编辑。',
        login_required: '登录已过期，请刷新页面重新登录。',
        csrf_failed: '登录验证失效，请刷新页面。',
        invalid_content: '内容格式有误，请检查链接、邮箱、日期和必填项。',
        too_many_attempts: '登录尝试过多，请五分钟后重试。',
        invalid_image: '仅支持有效的照片或动画文件。',
        file_too_large: '图片不能超过十二兆字节。'
      };
      throw Error(errors[result.error] || '操作失败，请稍后重试。');
    }
    return result;
  }

  function status(message, error = false) {
    const element = document.querySelector('#cms-status');
    if (element) {
      element.textContent = message;
      element.classList.toggle('error', error);
    }
  }

  function markDirty() {
    dirty = true;
    status('有未保存的修改。');
  }

  function get(path) {
    return path.split('.').reduce((value, key) => value[key], state);
  }

  function set(path, value) {
    const keys = path.split('.');
    const last = keys.pop();
    get(keys.join('.'))[last] = value;
    markDirty();
  }

  function field(path, value, label) {
    const key = path.split('.').pop();
    label = label || fieldNames[key] || key;
    if (value && typeof value === 'object' && !Array.isArray(value) && 'zh' in value) {
      const ready = value.en && value.hant;
      return `<label class="cms-field">${esc(label)}<textarea data-path="${path}.zh">${esc(value.zh)}</textarea><small>${ready?'英文与繁体内容已就绪；修改后保存会同步更新。':'保存时自动翻译；繁体中文本地生成；英文未配置服务时标记待翻译。'}</small></label>`;
    }
    if (['image', 'logo', 'heroLogo', 'opening'].includes(key)) {
      return `<div class="cms-field"><label>${esc(label)}<input data-path="${path}" value="${esc(value)}" placeholder="上传图片或填写图片网址"></label><div class="upload-row">${image(value,label,get(path.split('.').slice(0,-1).join('.'))?.crop)}<label class="button">上传图片<input class="upload-file" data-upload="${path}" type="file" accept="image/png,image/jpeg,image/gif,image/webp"></label><button type="button" data-clear="${path}">清除图片</button></div></div>`;
    }
    if (key === 'placement' || key === 'departmentDirection') {
      const options = key === 'placement' ? [
        ['qr', '二维码区'],
        ['account', '底部账号文字'],
        ['hidden', '暂不显示']
      ] : [
        ['up', '向上滚动'],
        ['down', '向下滚动']
      ];
      return `<label class="cms-field">${key==='placement'?'联系方式展示位置':fieldNames[key]}<select data-path="${path}">${options.map(([id,name])=>`<option value="${id}" ${value===id?'selected':''}>${name}</option>`).join('')}</select></label>`;
    }
    if (key === 'primaryColor' || key === 'backgroundColor') return `<label class="cms-field">${label}<input type="color" data-path="${path}" value="${esc(value)}"></label>`;
    if (key === 'page' || key === 'region' || key === 'category') {
      const options = key === 'page' ? Object.entries(state.pages).map(([id, p]) => ({
        id,
        name: p.title
      })) : state[key === 'region' ? 'regions' : 'categories'];
      return `<label class="cms-field">${key==='page'?'所属页面':key==='region'?'地区':'种类'}<select data-path="${path}"><option value="">请选择</option>${options.map(item=>`<option value="${esc(item.id)}" ${item.id===value?'selected':''}>${esc(item.name.zh)}</option>`).join('')}</select></label>`;
    }
    if (typeof value === 'boolean') return `<label class="cms-check"><input data-path="${path}" type="checkbox" ${value?'checked':''}>${esc(label)}</label>`;
    return `<label class="cms-field">${esc(label)}<input data-path="${path}" type="${typeof value==='number'?'number':key==='date'?'date':'text'}" value="${esc(value)}"></label>`;
  }

  function objectFields(path, object) {
    const order = ['name', 'title', 'page', 'date', 'role', 'description', 'text', 'intro', 'recruitment', 'year', 'image', 'region', 'category', 'url', 'account', 'published'];
    return Object.entries(object).sort(([first], [second]) => {
      const position = key => order.includes(key) ? order.indexOf(key) : 100;
      return position(first) - position(second);
    }).filter(([key]) => !['id', 'crop', 'tags', 'members'].includes(key)).map(([key, value]) => field(path + '.' + key, value)).join('');
  }

  function editorCard(path, entry, index, kind) {
    const title = entry.name?.zh || entry.title?.zh || '未命名内容';
    return `<details class="editor-card" ${index===0?'open':''}><summary>${index+1}. ${esc(title)}${kind==='posts'&&!entry.published?' · 草稿':''}</summary><div class="editor-body">${objectFields(path,entry)}${kind==='terms'?`<h3>本届成员</h3>${entry.members.map((member,i)=>editorCard(path+'.members.'+i,member,i,'member')).join('')}<button type="button" data-add-member="${path}.members">添加成员</button>`:''}<div class="editor-actions"><button type="button" data-move="${path}" data-direction="-1">上移</button><button type="button" data-move="${path}" data-direction="1">下移</button><button type="button" class="danger" data-delete="${path}">删除这条内容</button></div></div></details>`;
  }

  function contentEditor() {
    if (section === 'homeSections') return `<p class="cms-hint">用上下按钮调整首页次序；关闭显示会隐藏该区块。导航保持原有内容。</p>${state.homeSections.map((item,index)=>`<div class="section-order-row"><strong>${esc(item.name.zh)}</strong><label><input type="checkbox" data-path="homeSections.${index}.visible" ${item.visible?'checked':''}>显示</label><button data-move="homeSections.${index}" data-direction="-1">上移</button><button data-move="homeSections.${index}" data-direction="1">下移</button></div>`).join('')}`;

    if (['settings', 'layout', 'interfaceText'].includes(section)) return `<div class="editor-body">${objectFields(section,state[section])}</div>`;
    if (section === 'pages') return Object.entries(state.pages).map(([key, page]) => `<details class="editor-card"><summary>${esc(page.title.zh)}</summary><div class="editor-body">${field('pages.'+key+'.title',page.title)}${page.paragraphs.map((text,i)=>`<div>${field('pages.'+key+'.paragraphs.'+i,text,'正文段落 '+(i+1))}<button type="button" data-delete="pages.${key}.paragraphs.${i}">删除段落</button></div>`).join('')}<button type="button" data-add-paragraph="${key}">添加段落</button><p class="cms-hint">图片、附加文章和超链接请到“活动与文章”中选择此页面添加。关于我们在首页显示。</p></div></details>`).join('');
    const entries = state[section];
    return `<button type="button" class="button primary" id="add-entry">添加${names[section]}</button><p class="cms-hint">${section==='departments'?'每个部门只需填写一个超链接：首页详情按钮、招新页面详情按钮和导航栏“部门招新”同步使用。修改并保存发布后，刷新官网即可生效。留空时详情按钮不可点击，导航不跳转。':section==='terms'?'按排序年份倒序显示。现任资料在“现任主席团”编辑；每届可继续添加成员。':section==='posts'?'首页显示最新三个已发布活动。相同日期以列表靠后的内容为新。取消勾选发布可保留为草稿。':'修改后点击“保存并发布”才会写入网站。'}</p>${entries.map((entry,index)=>editorCard(section+'.'+index,entry,index,section)).join('')}`;
  }

  function render() {
    root().innerHTML = `<section class="cms"><div class="cms-heading"><div><h1>网站内容管理</h1><p>用中文编辑，统一维护三语网站。</p></div><a class="button" href="${esc(window.MCSA_CONFIG.frontendUrl)}" target="_blank" rel="noopener noreferrer">查看网站 ↗</a></div><div class="cms-toolbar"><button class="button primary" id="save-site">保存并发布</button><button class="button" id="preview-site">预览未保存修改</button><a class="button" href="/api/backup">下载内容备份</a><button id="logout">退出登录</button></div><p id="cms-status" role="status">${dirty?'有未保存的修改。':'内容已载入。'}</p><div class="cms-layout"><nav class="cms-tabs">${Object.entries(names).map(([key,name])=>`<button data-section="${key}" class="${section===key?'selected':''}">${name}</button>`).join('')}</nav><div class="cms-editor"><h2>${names[section]}</h2>${contentEditor()}</div></div></section>`;
    bind();
  }

  function remove(path) {
    if (!confirm('确定删除这条内容？保存后才会生效。')) return;
    const parts = path.split('.');
    const index = Number(parts.pop());
    const list = get(parts.join('.'));
    if (parts[0] === 'team' && list.length === 1) {
      status('现任主席团至少保留一位成员。', true);
      return;
    }
    if (['regions', 'categories'].includes(parts[0])) {
      const field = parts[0] === 'regions' ? 'region' : 'category';
      if (state.merchants.some(item => item[field] === list[index].id)) {
        status('这个筛选项仍被商家使用，请先修改相关商家的分类。', true);
        return;
      }
    }
    list.splice(index, 1);
    markDirty();
    render();
  }

  function bind() {
    document.querySelector('#preview-site').onclick = () => {
      const dialog = document.createElement('dialog');
      dialog.className = 'cms-preview';
      const frontend = new URL(window.MCSA_CONFIG.frontendUrl);
      const previewUrl = new URL('index.html?preview=1', frontend);
      dialog.innerHTML = `<div><strong>首页预览 · 当前编辑内容</strong><button type="button">关闭预览</button></div><iframe title="首页预览" src="${esc(previewUrl.href)}"></iframe>`;
      const frame = dialog.querySelector('iframe');
      function receive(event) {
        if (event.source !== frame.contentWindow || event.origin !== frontend.origin || event.data?.type !== 'mcsa-preview-ready') return;
        frame.contentWindow.postMessage({type: 'mcsa-preview-content', content: window.MCSA.previewContent(state)}, frontend.origin);
      }
      window.addEventListener('message', receive);
      document.body.append(dialog);
      dialog.showModal();
      function close() {
        window.removeEventListener('message', receive);
        dialog.remove();
      }
      dialog.querySelector('button').onclick = close;
      dialog.addEventListener('cancel', close);
    };

    root().querySelectorAll('[data-path]').forEach(input => input.oninput = () => {
      const current = get(input.dataset.path);
      set(input.dataset.path, input.type === 'checkbox' ? input.checked : typeof current === 'number' ? Number(input.value) : input.value);
    });
    root().querySelectorAll('[data-section]').forEach(button => button.onclick = () => {
      section = button.dataset.section;
      render();
    });
    root().querySelectorAll('[data-delete]').forEach(button => button.onclick = () => remove(button.dataset.delete));
    root().querySelectorAll('[data-clear]').forEach(button => button.onclick = () => {
      set(button.dataset.clear, '');
      render();
    });
    root().querySelectorAll('[data-move]').forEach(button => button.onclick = () => {
      const parts = button.dataset.move.split('.');
      const index = Number(parts.pop());
      const list = get(parts.join('.'));
      const target = index + Number(button.dataset.direction);
      if (target < 0 || target >= list.length) return;
      [list[index], list[target]] = [list[target], list[index]];
      markDirty();
      render();
    });
    root().querySelectorAll('[data-add-member]').forEach(button => button.onclick = () => {
      get(button.dataset.addMember).push(templates.member());
      markDirty();
      render();
    });
    root().querySelectorAll('[data-add-paragraph]').forEach(button => button.onclick = () => {
      state.pages[button.dataset.addParagraph].paragraphs.push(tri());
      markDirty();
      render();
    });
    root().querySelector('#add-entry')?.addEventListener('click', () => {
      state[section].push(templates[section]());
      markDirty();
      render();
      const cards = root().querySelectorAll('.editor-card');
      const last = cards[cards.length - 1];
      last.open = true;
      last.scrollIntoView({
        block: 'center'
      });
    });
    root().querySelectorAll('[data-upload]').forEach(input => input.onchange = async () => {
      if (!input.files[0]) return;
      const body = new FormData();
      body.append('file', input.files[0]);
      status('正在上传图片…');
      try {
        const result = await api('/upload', {
          method: 'POST',
          body
        });
        set(input.dataset.upload, result.url);
        const parent = get(input.dataset.upload.split('.').slice(0, -1).join('.'));
        if ('crop' in parent) parent.crop = null;
        if (input.dataset.upload === 'settings.opening' && result.duration) state.settings.openingDuration = result.duration;
        render();
        status('图片已上传，请保存以发布。');
      } catch (error) {
        status(error.message, true);
      }
    });
    document.querySelector('#save-site').onclick = async event => {
      const button = event.currentTarget;
      button.disabled = true;
      status('正在保存、翻译并发布，请稍候…');
      root().querySelector('.cms-layout').inert = true;
      try {
        const result = await api('/admin/site', {
          method: 'PUT',
          body: JSON.stringify({
            revision,
            data: state
          })
        });
        revision = result.revision;
        state = result.data;
        dirty = false;
        render();
        status(`已保存第 ${revision} 次更新。已勾选发布的文章和其他栏目将在官网下次打开或刷新时显示。` + (result.warnings.length ? ' ' + result.warnings.join(' ') : ''), result.warnings.length > 0);
      } catch (error) {
        status(error.message, true);
      } finally {
        button.disabled = false;
        root().querySelector('.cms-layout').inert = false;
      }
    };
    document.querySelector('#logout').onclick = async () => {
      if (dirty && !confirm('有未保存修改，仍然退出吗？')) return;
      await api('/logout', {
        method: 'POST'
      });
      dirty = false;
      location.reload();
    };
  }

  function login() {
    root().innerHTML = '<form class="cms-login"><h1>管理员登录</h1><p>登录后可以编辑网站所有栏目。</p><label>账号<input name="username" value="admin" autocomplete="username" required></label><label>密码<input name="password" type="password" autocomplete="current-password" required></label><button class="button primary">登录</button><p id="cms-status" role="status"></p></form>';
    root().querySelector('form').onsubmit = async event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      try {
        const result = await api('/login', {
          method: 'POST',
          body: JSON.stringify(Object.fromEntries(form))
        });
        csrf = result.csrf;
        await load();
      } catch (error) {
        status(error.message, true);
      }
    };
  }
  async function load() {
    const result = await api('/admin/site');
    state = result.data;
    revision = result.revision;
    render();
    const translation = await api('/translation-status');
    if (!translation.configured) status('英文翻译服务尚未配置。简繁中文可直接保存；已有英文正常显示。');
  }
  window.addEventListener('beforeunload', event => {
    if (dirty) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
  api('/session').then(result => {
    csrf = result.csrf;
    return result.authenticated ? load() : login();
  }).catch(error => {
    login();
    status(error.message, true);
  });
})();
