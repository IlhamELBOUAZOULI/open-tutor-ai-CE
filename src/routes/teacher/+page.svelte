<script>
  import { goto } from '$app/navigation';
  import { user } from '$lib/stores';
  import { onMount, getContext } from 'svelte';

  let loading = true;
  let activeTab = 'assignments';
  let assignments = [];
  let students = [];
  let classroom = null;
  let courses = [];
  let showModal = false;
  let showCourseModal = false;
  let showCourseViewer = false;
  let viewingCourse = null;
  let modalMode = 'create';
  let editingAssignment = null;
  let editingCourse = null;
  let successMsg = '';
  let uploading = false;
  let selectedFile = null;
  let filterModule = 'all';

  let form = { title: '', description: '', course: '', due_date: '', due_time: '23:59', points: 100 };
  let courseForm = { title: '', description: '', module: '' };

  const MODULES = [
    'Généralités sur les systèmes informatiques',
    'Logiciels',
    'Représentation de l\'information',
    'Algorithmique et programmation',
    'Réseaux informatiques',
    'Bases de données',
    'Systèmes d\'exploitation',
    'Sécurité informatique',
    'Internet et Web',
    'Autre',
  ];

  const i18n = getContext('i18n');
  const API = 'http://localhost:8080';

  function getToken() {
    try {
      const t = localStorage.getItem('token') || sessionStorage.getItem('token');
      if (t) return t.replace(/^"|"$/g, '');
    } catch(e) {}
    return null;
  }

  async function apiFetch(path, options = {}) {
    const t = getToken();
    const res = await fetch(`${API}${path}`, {
      ...options,
      headers: {
        ...(t ? { Authorization: `Bearer ${t}` } : {}),
        ...(options.headers || {})
      }
    });
    if (!res.ok) throw new Error(`${res.status}`);
    return res.json();
  }

  async function loadAll() {
    try { assignments = await apiFetch('/api/v1/assignments'); } catch { assignments = []; }
    try { students = await apiFetch('/api/v1/students'); } catch { students = []; }
    try { classroom = await apiFetch('/api/v1/classroom'); } catch { classroom = null; }
    try { courses = await apiFetch('/api/v1/courses'); } catch { courses = []; }
    loading = false;
  }

  // ── Assignments ──────────────────────────────
  function openCreate() {
    modalMode = 'create'; editingAssignment = null;
    form = { title: '', description: '', course: '', due_date: '', due_time: '23:59', points: 100 };
    showModal = true;
  }

  function openEdit(a) {
    modalMode = 'edit'; editingAssignment = a;
    form = { title: a.title, description: a.description||'', course: a.course||'', due_date: a.due_date, due_time: a.due_time||'23:59', points: a.points||100 };
    showModal = true;
  }

  async function submitForm() {
    try {
      if (modalMode === 'create') {
        await apiFetch('/api/v1/assignments', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(form) });
        showSuccess('Devoir créé !');
      } else {
        await apiFetch(`/api/v1/assignments/${editingAssignment.id}`, { method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify(form) });
        showSuccess('Devoir modifié !');
      }
      showModal = false;
      assignments = await apiFetch('/api/v1/assignments');
    } catch(e) { alert('Erreur: ' + e.message); }
  }

  async function deleteAssignment(id) {
    if (!confirm('Supprimer ce devoir ?')) return;
    try {
      await apiFetch(`/api/v1/assignments/${id}`, { method: 'DELETE' });
      assignments = assignments.filter(a => a.id !== id);
      showSuccess('Supprimé !');
    } catch(e) { alert('Erreur: ' + e.message); }
  }

  // ── Courses ───────────────────────────────────
  function openCreateCourse() {
    modalMode = 'create'; editingCourse = null; selectedFile = null;
    courseForm = { title: '', description: '', module: MODULES[0] };
    showCourseModal = true;
  }

  function openEditCourse(c) {
    modalMode = 'edit'; editingCourse = c; selectedFile = null;
    courseForm = { title: c.title, description: c.description||'', module: c.module||MODULES[0] };
    showCourseModal = true;
  }

  function handleFileSelect(e) {
    selectedFile = e.target.files[0];
  }

  async function submitCourseForm() {
    if (!courseForm.title) { alert('Le titre est obligatoire'); return; }
    if (modalMode === 'create' && !selectedFile) { alert('Veuillez sélectionner un fichier'); return; }

    uploading = true;
    try {
      const fd = new FormData();
      fd.append('title', courseForm.title);
      fd.append('description', courseForm.description);
      fd.append('module', courseForm.module);
      if (selectedFile) fd.append('file', selectedFile);

      const t = getToken();
      const url = modalMode === 'create'
        ? `${API}/api/v1/courses`
        : `${API}/api/v1/courses/${editingCourse.id}`;
      const method = modalMode === 'create' ? 'POST' : 'PUT';

      const res = await fetch(url, {
        method,
        headers: t ? { Authorization: `Bearer ${t}` } : {},
        body: fd
      });
      if (!res.ok) throw new Error(await res.text());

      showSuccess(modalMode === 'create' ? 'Cours créé !' : 'Cours modifié !');
      showCourseModal = false;
      courses = await apiFetch('/api/v1/courses');
    } catch(e) {
      alert('Erreur: ' + e.message);
    } finally {
      uploading = false;
    }
  }

  async function deleteCourse(id) {
    if (!confirm('Supprimer ce cours ?')) return;
    try {
      await apiFetch(`/api/v1/courses/${id}`, { method: 'DELETE' });
      courses = courses.filter(c => c.id !== id);
      showSuccess('Cours supprimé !');
    } catch(e) { alert('Erreur: ' + e.message); }
  }

  function viewCourse(c) {
    viewingCourse = c;
    showCourseViewer = true;
  }

  function downloadCourse(c) {
    const t = getToken();
    const url = `${API}/api/v1/courses/${c.id}/file`;
    const a = document.createElement('a');
    a.href = url + (t ? `?token=${t}` : '');
    a.download = c.original_filename || c.filename;
    a.click();
  }

  function getCourseFileUrl(c) {
    const t = getToken();
    return `${API}/api/v1/courses/${c.id}/file${t ? `?token=${t}` : ''}`;
  }

  // ── Classroom ─────────────────────────────────
  async function regenerateCode() {
    try { classroom = await apiFetch('/api/v1/classroom/regenerate', { method: 'POST' }); showSuccess('Nouveau code !'); }
    catch(e) { alert('Erreur: ' + e.message); }
  }

  function showSuccess(msg) { successMsg = msg; setTimeout(() => successMsg = '', 3000); }

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' o';
    if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' Ko';
    return (bytes/(1024*1024)).toFixed(1) + ' Mo';
  }

  function fileIcon(type) {
    if (type === '.pdf') return '📄';
    if (['.doc','.docx'].includes(type)) return '📝';
    if (['.ppt','.pptx'].includes(type)) return '📊';
    return '📁';
  }

  $: filteredCourses = filterModule === 'all' ? courses : courses.filter(c => c.module === filterModule);
  $: uniqueModules = [...new Set(courses.map(c => c.module))];

  onMount(async () => {
    if (!$user) { goto('/auth'); return; }
    if ($user.role !== 'teacher' && $user.role !== 'admin') { goto(`/${$user.role}`); return; }
    await loadAll();
  });
</script>

<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  .dash { min-height: 100vh; background: #0a0a0f; color: #e8e6f0; font-family: 'Segoe UI', sans-serif; }
  .header { background: #1a1025; border-bottom: 1px solid #2a1f3d; padding: 0 2rem; display: flex; align-items: center; justify-content: space-between; height: 60px; position: sticky; top: 0; z-index: 100; }
  .logo { font-size: 1.3rem; font-weight: 800; background: linear-gradient(135deg, #a78bfa, #f472b6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .user-badge { background: #1e1535; border: 1px solid #3d2d5e; border-radius: 20px; padding: 0.3rem 0.9rem; font-size: 0.82rem; color: #c4b5fd; }
  .layout { display: flex; min-height: calc(100vh - 60px); }
  .sidebar { width: 210px; background: #0f0f1a; border-right: 1px solid #1e1535; padding: 1rem 0; flex-shrink: 0; }
  .nav-item { display: flex; align-items: center; gap: 0.6rem; padding: 0.7rem 1.4rem; cursor: pointer; border-left: 3px solid transparent; font-size: 0.88rem; color: #8b7fa8; font-weight: 500; transition: all 0.2s; }
  .nav-item:hover { background: #1a1030; color: #c4b5fd; }
  .nav-item.active { background: #1e1535; color: #a78bfa; border-left-color: #a78bfa; }
  .main { flex: 1; padding: 1.5rem 2rem; min-width: 0; }
  .page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 0.75rem; }
  .page-title { font-size: 1.6rem; font-weight: 700; color: #f0edf8; }
  .page-sub { font-size: 0.82rem; color: #6b5f85; margin-top: 0.2rem; }
  .btn { padding: 0.55rem 1.1rem; border-radius: 8px; border: none; cursor: pointer; font-weight: 600; font-size: 0.85rem; transition: all 0.2s; font-family: inherit; display: inline-flex; align-items: center; gap: 0.4rem; }
  .btn:disabled { opacity: 0.6; cursor: not-allowed; }
  .btn-primary { background: linear-gradient(135deg, #7c3aed, #a855f7); color: white; box-shadow: 0 4px 12px rgba(124,58,237,0.3); }
  .btn-primary:hover:not(:disabled) { transform: translateY(-1px); }
  .btn-danger { background: #2d1515; color: #f87171; border: 1px solid #3d2020; }
  .btn-ghost { background: #1e1535; color: #a78bfa; border: 1px solid #3d2d5e; }
  .btn-green { background: #052e16; color: #22c55e; border: 1px solid #166534; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px,1fr)); gap: 1rem; margin-bottom: 1.5rem; }
  .stat { background: #13101f; border: 1px solid #1e1535; border-radius: 10px; padding: 1rem; text-align: center; }
  .stat-num { font-size: 1.8rem; font-weight: 800; background: linear-gradient(135deg,#a78bfa,#f472b6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .stat-label { font-size: 0.72rem; color: #6b5f85; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 0.2rem; }
  .acard { background: #13101f; border: 1px solid #1e1535; border-radius: 10px; padding: 1rem 1.25rem; display: flex; align-items: center; gap: 1rem; margin-bottom: 0.6rem; transition: border-color 0.2s; }
  .acard:hover { border-color: #3d2d5e; }
  .ainfo { flex: 1; min-width: 0; }
  .atitle { font-weight: 600; color: #e8e6f0; margin-bottom: 0.2rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .ameta { font-size: 0.78rem; color: #6b5f85; display: flex; gap: 0.8rem; flex-wrap: wrap; margin-top: 0.25rem; }
  .adesc { font-size: 0.82rem; color: #8b7fa8; margin-top: 0.2rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .badge { display: inline-flex; padding: 0.15rem 0.5rem; border-radius: 20px; font-size: 0.72rem; font-weight: 600; white-space: nowrap; }
  .badge-active { background: #052e16; color: #22c55e; border: 1px solid #166534; }
  .badge-closed { background: #2d1515; color: #f87171; border: 1px solid #991b1b; }
  .badge-module { background: #1e1b4b; color: #818cf8; border: 1px solid #3730a3; font-size: 0.7rem; }
  .actions { display: flex; gap: 0.4rem; flex-shrink: 0; }
  .table-wrap { overflow-x: auto; border-radius: 10px; border: 1px solid #1e1535; }
  table { width: 100%; border-collapse: collapse; }
  th { background: #0f0f1a; padding: 0.65rem 1rem; text-align: left; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.5px; color: #6b5f85; border-bottom: 1px solid #1e1535; }
  td { padding: 0.8rem 1rem; border-bottom: 1px solid #13101f; font-size: 0.87rem; color: #c4b5fd; }
  tr:last-child td { border-bottom: none; }
  .code-box { font-size: 2.5rem; font-weight: 800; letter-spacing: 0.5rem; background: linear-gradient(135deg,#a78bfa,#f472b6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-align: center; padding: 1.5rem 0; }
  .card { background: #13101f; border: 1px solid #1e1535; border-radius: 12px; padding: 1.5rem; }
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.75); backdrop-filter: blur(4px); z-index: 200; display: flex; align-items: center; justify-content: center; padding: 1rem; }
  .modal { background: #13101f; border: 1px solid #3d2d5e; border-radius: 14px; padding: 1.75rem; width: 100%; max-width: 520px; max-height: 90vh; overflow-y: auto; }
  .modal-lg { max-width: 900px; height: 85vh; display: flex; flex-direction: column; }
  .modal-title { font-size: 1.25rem; font-weight: 700; color: #f0edf8; margin-bottom: 1.25rem; }
  .fg { margin-bottom: 0.85rem; }
  label { display: block; font-size: 0.73rem; font-weight: 600; color: #8b7fa8; margin-bottom: 0.3rem; text-transform: uppercase; letter-spacing: 0.4px; }
  input, textarea, select { width: 100%; background: #0a0a0f; border: 1px solid #2a1f3d; border-radius: 7px; padding: 0.6rem 0.8rem; color: #e8e6f0; font-size: 0.87rem; outline: none; transition: border-color 0.2s; font-family: inherit; }
  input:focus, textarea:focus, select:focus { border-color: #7c3aed; }
  select option { background: #13101f; }
  textarea { resize: vertical; min-height: 80px; }
  .frow { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
  .mactions { display: flex; gap: 0.6rem; justify-content: flex-end; margin-top: 1.25rem; }
  .toast { position: fixed; bottom: 1.5rem; right: 1.5rem; background: #052e16; border: 1px solid #166534; color: #22c55e; padding: 0.75rem 1rem; border-radius: 8px; font-weight: 600; font-size: 0.87rem; z-index: 300; animation: fadeIn 0.3s ease; }
  @keyframes fadeIn { from { opacity:0; transform: translateY(8px); } to { opacity:1; transform: translateY(0); } }
  .empty { text-align: center; padding: 2.5rem; color: #4a3d65; font-size: 0.95rem; }
  .spin { display: flex; align-items: center; justify-content: center; height: 200px; color: #6b5f85; }

  /* Courses grid */
  .filter-bar { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1.25rem; }
  .filter-btn { padding: 0.35rem 0.8rem; border-radius: 20px; border: 1px solid #2a1f3d; background: #13101f; color: #8b7fa8; font-size: 0.78rem; cursor: pointer; font-family: inherit; transition: all 0.2s; }
  .filter-btn.active { background: #1e1535; color: #a78bfa; border-color: #3d2d5e; }
  .courses-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 1rem; }
  .course-card { background: #13101f; border: 1px solid #1e1535; border-radius: 12px; padding: 1.25rem; transition: border-color 0.2s; display: flex; flex-direction: column; gap: 0.75rem; }
  .course-card:hover { border-color: #3d2d5e; }
  .course-icon { font-size: 2rem; }
  .course-name { font-weight: 700; font-size: 0.95rem; color: #e8e6f0; line-height: 1.4; }
  .course-desc { font-size: 0.8rem; color: #6b5f85; line-height: 1.5; flex: 1; }
  .course-meta { font-size: 0.75rem; color: #4a3d65; display: flex; gap: 0.75rem; flex-wrap: wrap; }
  .course-actions { display: flex; gap: 0.4rem; flex-wrap: wrap; }

  /* File upload zone */
  .upload-zone { border: 2px dashed #2a1f3d; border-radius: 10px; padding: 1.5rem; text-align: center; cursor: pointer; transition: border-color 0.2s; background: #0a0a0f; }
  .upload-zone:hover { border-color: #7c3aed; }
  .upload-zone.has-file { border-color: #22c55e; background: #052e16; }
  .upload-label { font-size: 0.85rem; color: #6b5f85; margin-top: 0.5rem; }
  .upload-input { display: none; }

  /* PDF viewer */
  .viewer-body { flex: 1; min-height: 0; }
  .pdf-frame { width: 100%; height: 100%; border: none; border-radius: 8px; }
  .viewer-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; }
  .viewer-title { font-size: 1.1rem; font-weight: 700; color: #f0edf8; }
</style>

<div class="dash">
  <header class="header">
    <div class="logo">OpenTutorAI</div>
    {#if $user}<span class="user-badge">👤 {$user.name}</span>{/if}
  </header>

  <div class="layout">
    <aside class="sidebar">
      {#each [
        {id:'assignments', icon:'📋', label:'Devoirs'},
        {id:'courses',     icon:'📚', label:'Cours'},
        {id:'students',    icon:'👥', label:'Étudiants'},
        {id:'classroom',   icon:'🏫', label:'Ma Classe'},
      ] as tab}
        <div class="nav-item {activeTab===tab.id?'active':''}" on:click={()=>activeTab=tab.id}>
          {tab.icon} {tab.label}
        </div>
      {/each}
    </aside>

    <main class="main">
      {#if loading}
        <div class="spin">⏳ Chargement...</div>

      <!-- ═══════════════ DEVOIRS ═══════════════ -->
      {:else if activeTab==='assignments'}
        <div class="page-header">
          <div><div class="page-title">📋 Devoirs</div><div class="page-sub">{assignments.length} devoir(s)</div></div>
          <button class="btn btn-primary" on:click={openCreate}>+ Nouveau devoir</button>
        </div>
        <div class="stats">
          <div class="stat"><div class="stat-num">{assignments.length}</div><div class="stat-label">Total</div></div>
          <div class="stat"><div class="stat-num">{assignments.filter(a=>a.status==='active').length}</div><div class="stat-label">Actifs</div></div>
          <div class="stat"><div class="stat-num">{assignments.reduce((s,a)=>s+(a.submission_count||0),0)}</div><div class="stat-label">Soumissions</div></div>
          <div class="stat"><div class="stat-num">{students.length}</div><div class="stat-label">Étudiants</div></div>
        </div>
        {#if assignments.length===0}
          <div class="empty">📋 Aucun devoir. Créez votre premier devoir !</div>
        {:else}
          {#each assignments as a}
            <div class="acard">
              <div class="ainfo">
                <div class="atitle">{a.title}</div>
                {#if a.description}<div class="adesc">{a.description}</div>{/if}
                <div class="ameta">
                  {#if a.course}<span>📚 {a.course}</span>{/if}
                  <span>📅 {a.due_date} à {a.due_time}</span>
                  <span>⭐ {a.points} pts</span>
                  <span>📨 {a.submission_count||0} soumissions</span>
                </div>
              </div>
              <span class="badge badge-{a.status||'active'}">{a.status==='active'?'Actif':'Fermé'}</span>
              <div class="actions">
                <button class="btn btn-ghost" on:click={()=>openEdit(a)}>✏️</button>
                <button class="btn btn-danger" on:click={()=>deleteAssignment(a.id)}>🗑️</button>
              </div>
            </div>
          {/each}
        {/if}

      <!-- ═══════════════ COURS ═══════════════ -->
      {:else if activeTab==='courses'}
        <div class="page-header">
          <div><div class="page-title">📚 Cours</div><div class="page-sub">{courses.length} cours créé(s)</div></div>
          <button class="btn btn-primary" on:click={openCreateCourse}>+ Nouveau cours</button>
        </div>

        <!-- Filtre par module -->
        {#if courses.length > 0}
          <div class="filter-bar">
            <button class="filter-btn {filterModule==='all'?'active':''}" on:click={()=>filterModule='all'}>Tous</button>
            {#each uniqueModules as m}
              <button class="filter-btn {filterModule===m?'active':''}" on:click={()=>filterModule=m}>{m}</button>
            {/each}
          </div>
        {/if}

        {#if filteredCourses.length===0}
          <div class="empty">📚 Aucun cours. Créez votre premier cours avec un fichier PDF !</div>
        {:else}
          <div class="courses-grid">
            {#each filteredCourses as c}
              <div class="course-card">
                <div style="display:flex;align-items:center;justify-content:space-between">
                  <span class="course-icon">{fileIcon(c.file_type)}</span>
                  <span class="badge badge-module">{c.module}</span>
                </div>
                <div class="course-name">{c.title}</div>
                <div class="course-desc">{c.description || 'Aucune description'}</div>
                <div class="course-meta">
                  <span>📦 {formatSize(c.file_size)}</span>
                  <span>👤 {c.teacher_name || 'Enseignant'}</span>
                </div>
                <div class="course-actions">
                  <button class="btn btn-green" style="flex:1" on:click={()=>viewCourse(c)}>👁️ Lire</button>
                  <button class="btn btn-ghost" on:click={()=>downloadCourse(c)}>⬇️</button>
                  <button class="btn btn-ghost" on:click={()=>openEditCourse(c)}>✏️</button>
                  <button class="btn btn-danger" on:click={()=>deleteCourse(c.id)}>🗑️</button>
                </div>
              </div>
            {/each}
          </div>
        {/if}

      <!-- ═══════════════ ÉTUDIANTS ═══════════════ -->
      {:else if activeTab==='students'}
        <div class="page-header">
          <div><div class="page-title">👥 Étudiants</div><div class="page-sub">{students.length} étudiant(s)</div></div>
        </div>
        {#if students.length===0}
          <div class="empty">👥 Aucun étudiant.</div>
        {:else}
          <div class="table-wrap">
            <table>
              <thead><tr><th>Nom</th><th>Email</th><th>Rôle</th></tr></thead>
              <tbody>
                {#each students as s}
                  <tr>
                    <td>👤 {s.name}</td>
                    <td>{s.email}</td>
                    <td><span class="badge badge-active">{s.role}</span></td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}

      <!-- ═══════════════ MA CLASSE ═══════════════ -->
      {:else if activeTab==='classroom'}
        <div class="page-header">
          <div><div class="page-title">🏫 Ma Classe</div><div class="page-sub">Code pour vos étudiants</div></div>
          <button class="btn btn-ghost" on:click={regenerateCode}>🔄 Nouveau code</button>
        </div>
        {#if classroom}
          <div class="card" style="max-width:420px;margin:0 auto;text-align:center">
            <div style="font-size:0.75rem;color:#6b5f85;text-transform:uppercase;letter-spacing:1px">Code de classe</div>
            <div class="code-box">{classroom.class_code}</div>
            <div style="font-size:0.82rem;color:#6b5f85;margin-bottom:1rem">Partagez ce code avec vos étudiants pour rejoindre votre classe.</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;text-align:left">
              <div><div style="font-size:0.72rem;color:#6b5f85;text-transform:uppercase">Nom</div><div style="color:#c4b5fd">{classroom.name||'Ma classe'}</div></div>
              <div><div style="font-size:0.72rem;color:#6b5f85;text-transform:uppercase">Étudiants</div><div style="color:#c4b5fd">{classroom.student_count||0}</div></div>
            </div>
          </div>
        {:else}
          <div class="empty">🏫 Impossible de charger la classe.</div>
        {/if}
      {/if}
    </main>
  </div>
</div>

<!-- ═══ Modal Devoirs ═══ -->
{#if showModal}
  <div class="overlay" on:click|self={()=>showModal=false}>
    <div class="modal">
      <div class="modal-title">{modalMode==='create'?'➕ Nouveau devoir':'✏️ Modifier le devoir'}</div>
      <div class="fg"><label>Titre *</label><input bind:value={form.title} placeholder="Titre du devoir"/></div>
      <div class="fg"><label>Description</label><textarea bind:value={form.description} placeholder="Instructions pour les étudiants..."></textarea></div>
      <div class="fg"><label>Cours / Matière</label><input bind:value={form.course} placeholder="Ex: Mathématiques"/></div>
      <div class="frow">
        <div class="fg"><label>Date limite *</label><input type="date" bind:value={form.due_date}/></div>
        <div class="fg"><label>Heure limite</label><input type="time" bind:value={form.due_time}/></div>
      </div>
      <div class="fg"><label>Points</label><input type="number" bind:value={form.points} min="0"/></div>
      <div class="mactions">
        <button class="btn btn-ghost" on:click={()=>showModal=false}>Annuler</button>
        <button class="btn btn-primary" on:click={submitForm}>{modalMode==='create'?'Créer':'Enregistrer'}</button>
      </div>
    </div>
  </div>
{/if}

<!-- ═══ Modal Cours ═══ -->
{#if showCourseModal}
  <div class="overlay" on:click|self={()=>showCourseModal=false}>
    <div class="modal">
      <div class="modal-title">{modalMode==='create'?'📚 Nouveau cours':'✏️ Modifier le cours'}</div>

      <div class="fg">
        <label>Titre du cours *</label>
        <input bind:value={courseForm.title} placeholder="Ex: Introduction aux systèmes informatiques"/>
      </div>

      <div class="fg">
        <label>Description</label>
        <textarea bind:value={courseForm.description} placeholder="Objectifs du cours, contenu, prérequis..."></textarea>
      </div>

      <div class="fg">
        <label>Module (Tronc commun informatique) *</label>
        <select bind:value={courseForm.module}>
          {#each MODULES as m}
            <option value={m}>{m}</option>
          {/each}
        </select>
      </div>

      <div class="fg">
        <label>Fichier du cours {modalMode==='create'?'*':'(laisser vide pour garder l\'actuel)'}</label>
        <label class="upload-zone {selectedFile?'has-file':''}" for="file-input">
          {#if selectedFile}
            <div style="font-size:1.5rem">✅</div>
            <div style="color:#22c55e;font-weight:600;margin-top:0.5rem">{selectedFile.name}</div>
            <div style="font-size:0.75rem;color:#6b5f85;margin-top:0.25rem">{formatSize(selectedFile.size)}</div>
          {:else}
            <div style="font-size:1.5rem">📎</div>
            <div class="upload-label">Cliquez pour sélectionner un fichier</div>
            <div style="font-size:0.72rem;color:#4a3d65;margin-top:0.25rem">PDF, Word, PowerPoint, TXT</div>
          {/if}
        </label>
        <input id="file-input" class="upload-input" type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.txt" on:change={handleFileSelect}/>
      </div>

      <div class="mactions">
        <button class="btn btn-ghost" on:click={()=>showCourseModal=false}>Annuler</button>
        <button class="btn btn-primary" on:click={submitCourseForm} disabled={uploading}>
          {uploading ? '⏳ Envoi...' : modalMode==='create' ? 'Créer le cours' : 'Enregistrer'}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- ═══ Viewer PDF ═══ -->
{#if showCourseViewer && viewingCourse}
  <div class="overlay" on:click|self={()=>showCourseViewer=false}>
    <div class="modal modal-lg">
      <div class="viewer-header">
        <div>
          <div class="viewer-title">{fileIcon(viewingCourse.file_type)} {viewingCourse.title}</div>
          <div style="font-size:0.75rem;color:#6b5f85">{viewingCourse.module}</div>
        </div>
        <div style="display:flex;gap:0.5rem">
          <button class="btn btn-ghost" on:click={()=>downloadCourse(viewingCourse)}>⬇️ Télécharger</button>
          <button class="btn btn-danger" on:click={()=>showCourseViewer=false}>✕ Fermer</button>
        </div>
      </div>
      <div class="viewer-body">
        {#if viewingCourse.file_type === '.pdf'}
          <iframe class="pdf-frame" src="{getCourseFileUrl(viewingCourse)}" title={viewingCourse.title}></iframe>
        {:else}
          <div class="empty" style="height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center">
            <div style="font-size:3rem">{fileIcon(viewingCourse.file_type)}</div>
            <div style="margin-top:1rem;color:#8b7fa8">Ce type de fichier ne peut pas être prévisualisé directement.</div>
            <button class="btn btn-primary" style="margin-top:1rem" on:click={()=>downloadCourse(viewingCourse)}>⬇️ Télécharger pour ouvrir</button>
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}

{#if successMsg}<div class="toast">✅ {successMsg}</div>{/if}