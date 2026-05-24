<script lang="ts">
  import { goto } from '$app/navigation';
  import { user } from '$lib/stores';
  import { onMount } from 'svelte';

  let loading = true;
  let activeTab = 'assignments';
  let assignments: any[] = [];
  let courses: any[] = [];
  let classrooms: any[] = [];
  let selectedPdf: { url: string; title: string } | null = null;

  const API = 'http://localhost:8080';

  function getToken(): string | null {
    try {
      const t = localStorage.getItem('token') || sessionStorage.getItem('token');
      if (t) return t.replace(/^"|"$/g, '');
    } catch (e) {}
    return null;
  }

  async function apiFetch(path: string, options: RequestInit = {}) {
    const t = getToken();
    const res = await fetch(`${API}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(t ? { Authorization: `Bearer ${t}` } : {}),
        ...(options.headers || {})
      }
    });
    if (!res.ok) throw new Error(`${res.status}`);
    return res.json();
  }

  async function loadAll() {
    // 1. Get student's classrooms
    try {
      classrooms = await apiFetch('/api/v1/my-classrooms');
    } catch {
      classrooms = [];
    }

    // 2. For each classroom, load assignments and courses
    const allAssignments: any[] = [];
    const allCourses: any[] = [];

    for (const classroom of classrooms) {
      const code = classroom.class_code || classroom.code;
      if (!code) continue;

      try {
        const a = await apiFetch(`/api/v1/classroom/${code}/assignments`);
        allAssignments.push(...(Array.isArray(a) ? a : []));
      } catch {}

      try {
        const c = await apiFetch(`/api/v1/classroom/${code}/courses`);
        allCourses.push(...(Array.isArray(c) ? c : []));
      } catch {}
    }

    assignments = allAssignments;
    courses = allCourses;
    loading = false;
  }

  function getDaysLeft(due_date: string): string {
    if (!due_date) return '';
    const diff = Math.ceil((new Date(due_date).getTime() - Date.now()) / 86400000);
    if (diff < 0) return 'Expiré';
    if (diff === 0) return "Aujourd'hui";
    if (diff === 1) return 'Demain';
    return `${diff} jours`;
  }

  function getDaysClass(due_date: string): string {
    if (!due_date) return '';
    const diff = Math.ceil((new Date(due_date).getTime() - Date.now()) / 86400000);
    if (diff < 0) return 'expired';
    if (diff <= 2) return 'urgent';
    return 'ok';
  }

  function openPdf(url: string, title: string) {
    selectedPdf = { url, title };
  }

  function closePdf() {
    selectedPdf = null;
  }

  async function downloadPdf(url: string, filename: string) {
    const t = getToken();
    try {
      const res = await fetch(url, {
        headers: t ? { Authorization: `Bearer ${t}` } : {}
      });
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename || 'document.pdf';
      a.click();
      URL.revokeObjectURL(a.href);
    } catch {
      window.open(url, '_blank');
    }
  }

  onMount(async () => {
    if (!$user) { goto('/auth'); return; }
    if ($user.role !== 'user') { goto(`/${$user.role}`); return; }
    await loadAll();
  });
</script>

<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  .dash { min-height: 100vh; background: #020b15; color: #cfe4f5; font-family: 'DM Sans', 'Segoe UI', sans-serif; }
  .header { background: #030f1f; border-bottom: 1px solid #0b2d4e; padding: 0 2rem; display: flex; align-items: center; justify-content: space-between; height: 60px; position: sticky; top: 0; z-index: 100; }
  .logo { font-size: 1.3rem; font-weight: 800; color: #3b9eff; letter-spacing: -0.5px; }
  .logo span { color: #7ec8ff; }
  .user-badge { background: #041529; border: 1px solid #0b3a6e; border-radius: 20px; padding: 0.3rem 0.9rem; font-size: 0.82rem; color: #7ec8ff; }
  .layout { display: flex; min-height: calc(100vh - 60px); }
  .sidebar { width: 210px; background: #020d1a; border-right: 1px solid #0b2440; padding: 1rem 0; flex-shrink: 0; }
  .nav-item { display: flex; align-items: center; gap: 0.6rem; padding: 0.7rem 1.4rem; cursor: pointer; border-left: 3px solid transparent; font-size: 0.88rem; color: #3a6e99; font-weight: 500; transition: all 0.2s; }
  .nav-item:hover { background: #041829; color: #7ec8ff; }
  .nav-item.active { background: #041e38; color: #3b9eff; border-left-color: #3b9eff; }
  .main { flex: 1; padding: 1.5rem 2rem; overflow-y: auto; }
  .page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.5rem; }
  .page-title { font-size: 1.6rem; font-weight: 700; color: #e8f4ff; }
  .page-sub { font-size: 0.82rem; color: #2a5f8f; margin-top: 0.2rem; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
  .stat { background: #030f1e; border: 1px solid #0b2440; border-radius: 10px; padding: 1rem; text-align: center; }
  .stat-num { font-size: 1.8rem; font-weight: 800; color: #3b9eff; }
  .stat-label { font-size: 0.72rem; color: #2a5f8f; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 0.2rem; }
  .acard { background: #030f1e; border: 1px solid #0b2440; border-radius: 10px; padding: 1rem 1.25rem; display: flex; align-items: center; gap: 1rem; margin-bottom: 0.6rem; transition: border-color 0.2s; }
  .acard:hover { border-color: #0b3a6e; }
  .ainfo { flex: 1; }
  .atitle { font-weight: 600; color: #e8f4ff; margin-bottom: 0.2rem; font-size: 0.95rem; }
  .ameta { font-size: 0.78rem; color: #2a5f8f; display: flex; gap: 0.8rem; flex-wrap: wrap; margin-top: 0.25rem; }
  .deadline { display: inline-flex; align-items: center; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.72rem; font-weight: 700; white-space: nowrap; flex-shrink: 0; }
  .deadline.ok { background: #041e38; color: #3b9eff; border: 1px solid #0b3a6e; }
  .deadline.urgent { background: #2d1a00; color: #ffb74d; border: 1px solid #5d3a00; }
  .deadline.expired { background: #1a0505; color: #ef9a9a; border: 1px solid #4a1010; }
  .btn-submit { padding: 0.45rem 0.9rem; border-radius: 8px; border: none; cursor: pointer; font-weight: 600; font-size: 0.82rem; background: #1565c0; color: #e3f2fd; transition: all 0.2s; white-space: nowrap; flex-shrink: 0; }
  .btn-submit:hover { background: #1976d2; }
  .btn-submit:disabled { background: #0b2440; color: #2a5f8f; cursor: not-allowed; }
  .btn-pdf { padding: 0.35rem 0.75rem; border-radius: 7px; border: 1px solid #0b3a6e; cursor: pointer; font-weight: 600; font-size: 0.78rem; background: #041829; color: #7ec8ff; transition: all 0.2s; white-space: nowrap; display: inline-flex; align-items: center; gap: 0.35rem; }
  .btn-pdf:hover { background: #052840; border-color: #3b9eff; color: #3b9eff; }
  .btn-dl { padding: 0.35rem 0.75rem; border-radius: 7px; border: 1px solid #1b5e20; cursor: pointer; font-weight: 600; font-size: 0.78rem; background: #041829; color: #4caf50; transition: all 0.2s; white-space: nowrap; display: inline-flex; align-items: center; gap: 0.35rem; }
  .btn-dl:hover { background: #052e16; border-color: #4caf50; }
  .ccard { background: #030f1e; border: 1px solid #0b2440; border-radius: 10px; padding: 1rem 1.25rem; display: flex; align-items: flex-start; gap: 1rem; margin-bottom: 0.6rem; transition: border-color 0.2s; }
  .ccard:hover { border-color: #0b3a6e; }
  .cicon { width: 46px; height: 46px; border-radius: 10px; background: #041829; border: 1px solid #0b3a6e; display: flex; align-items: center; justify-content: center; font-size: 1.3rem; flex-shrink: 0; }
  .ctag { display: inline-flex; align-items: center; gap: 3px; padding: 0.12rem 0.45rem; border-radius: 6px; font-size: 0.7rem; font-weight: 600; background: #041829; color: #3b9eff; border: 1px solid #0b3a6e; margin-right: 0.25rem; }
  .badge-active { display: inline-flex; padding: 0.15rem 0.5rem; border-radius: 20px; font-size: 0.72rem; font-weight: 600; background: #052e16; color: #4caf50; border: 1px solid #1b5e20; white-space: nowrap; flex-shrink: 0; align-self: flex-start; }
  .pdf-list { margin-top: 0.75rem; display: flex; flex-direction: column; gap: 0.4rem; }
  .pdf-item { display: flex; align-items: center; gap: 0.5rem; background: #020d1a; border: 1px solid #0b2440; border-radius: 8px; padding: 0.5rem 0.75rem; }
  .pdf-name { flex: 1; font-size: 0.8rem; color: #7ec8ff; display: flex; align-items: center; gap: 0.4rem; }
  .pdf-actions { display: flex; gap: 0.4rem; }
  .progress-wrap { margin-top: 0.5rem; background: #041829; border-radius: 20px; height: 5px; overflow: hidden; width: 100%; }
  .progress-bar { height: 100%; border-radius: 20px; background: linear-gradient(90deg, #1565c0, #3b9eff); transition: width 0.5s ease; }
  .empty { text-align: center; padding: 3rem; color: #1a4a6e; font-size: 0.9rem; line-height: 2; }
  .spin { display: flex; align-items: center; justify-content: center; height: 200px; color: #2a5f8f; }
  .welcome { background: #030f1e; border: 1px solid #0b2440; border-left: 4px solid #3b9eff; border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 1.5rem; font-size: 0.9rem; color: #7ec8ff; }
  .welcome strong { color: #e8f4ff; }
  .no-class { background: #030f1e; border: 1px solid #0b2440; border-left: 4px solid #ffb74d; border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 1.5rem; font-size: 0.9rem; color: #ffb74d; }
  .pdf-modal-backdrop { position: fixed; inset: 0; background: rgba(2,11,21,0.92); z-index: 999; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; padding: 1.5rem; }
  .pdf-modal { width: 100%; max-width: 900px; height: calc(100vh - 3rem); display: flex; flex-direction: column; background: #020d1a; border: 1px solid #0b3a6e; border-radius: 14px; overflow: hidden; }
  .pdf-modal-header { display: flex; align-items: center; justify-content: space-between; padding: 0.75rem 1.25rem; background: #030f1f; border-bottom: 1px solid #0b2440; flex-shrink: 0; }
  .pdf-modal-title { font-size: 0.92rem; font-weight: 600; color: #e8f4ff; display: flex; align-items: center; gap: 0.5rem; }
  .pdf-modal-actions { display: flex; gap: 0.5rem; align-items: center; }
  .btn-close { background: #1a0505; color: #ef9a9a; border: 1px solid #4a1010; border-radius: 7px; padding: 0.35rem 0.75rem; font-size: 0.8rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }
  .btn-close:hover { background: #2d0a0a; }
  .pdf-iframe { flex: 1; width: 100%; border: none; background: #fff; }
</style>

<div class="dash">
  <header class="header">
    <div class="logo">Open<span>TutorAI</span></div>
    {#if $user}
      <span class="user-badge">🎓 {$user.name}</span>
    {/if}
  </header>

  <div class="layout">
    <aside class="sidebar">
      {#each [
        { id: 'assignments', icon: '📋', label: 'Mes Devoirs' },
        { id: 'courses',     icon: '📚', label: 'Mes Cours'   }
      ] as tab}
        <div
          class="nav-item {activeTab === tab.id ? 'active' : ''}"
          on:click={() => activeTab = tab.id}
          role="button"
          tabindex="0"
        >
          {tab.icon} {tab.label}
        </div>
      {/each}
    </aside>

    <main class="main">
      {#if loading}
        <div class="spin">⏳ Chargement...</div>

      {:else if activeTab === 'assignments'}
        <div class="page-header">
          <div>
            <div class="page-title">Mes Devoirs</div>
            <div class="page-sub">{assignments.length} devoir(s) disponible(s)</div>
          </div>
        </div>

        {#if $user}
          <div class="welcome">
            Bonjour <strong>{$user.name}</strong> 👋 — Voici vos devoirs à rendre.
          </div>
        {/if}

        {#if classrooms.length === 0}
          <div class="no-class">
            ⚠️ Vous n'êtes inscrit à aucune classe. Demandez à votre professeur votre code de classe.
          </div>
        {/if}

        <div class="stats">
          <div class="stat"><div class="stat-num">{assignments.length}</div><div class="stat-label">Total</div></div>
          <div class="stat"><div class="stat-num">{assignments.filter(a => a.status === 'active').length}</div><div class="stat-label">Actifs</div></div>
          <div class="stat"><div class="stat-num">{assignments.filter(a => (a.submission_count || 0) > 0).length}</div><div class="stat-label">Soumis</div></div>
          <div class="stat">
            <div class="stat-num">{assignments.filter(a => { const d = Math.ceil((new Date(a.due_date).getTime() - Date.now()) / 86400000); return d >= 0 && d <= 3; }).length}</div>
            <div class="stat-label">Urgents</div>
          </div>
        </div>

        {#if assignments.length === 0}
          <div class="empty">📋<br>Aucun devoir disponible pour le moment.<br>Revenez plus tard !</div>
        {:else}
          {#each assignments as a}
            <div class="acard">
              <div class="ainfo">
                <div class="atitle">{a.title}</div>
                {#if a.description}<div style="font-size:0.8rem;color:#4a7fa8;margin:0.2rem 0">{a.description}</div>{/if}
                <div class="ameta">
                  {#if a.course}<span>📚 {a.course}</span>{/if}
                  <span>📅 {a.due_date}{a.due_time ? ' à ' + a.due_time : ''}</span>
                  <span>⏰ {getDaysLeft(a.due_date)}</span>
                </div>
                {#if a.pdfs && a.pdfs.length > 0}
                  <div class="pdf-list">
                    {#each a.pdfs as pdf}
                      <div class="pdf-item">
                        <span class="pdf-name">📄 {pdf.title || pdf.filename || 'Document'}</span>
                        <div class="pdf-actions">
                          <button class="btn-pdf" on:click={() => openPdf(`${API}${pdf.url}`, pdf.title || pdf.filename)}>👁 Lire</button>
                          <button class="btn-dl" on:click={() => downloadPdf(`${API}${pdf.url}`, pdf.filename || 'document.pdf')}>⬇ Télécharger</button>
                        </div>
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
              <span class="deadline {getDaysClass(a.due_date)}">{getDaysLeft(a.due_date)}</span>
              <button class="btn-submit" disabled={getDaysClass(a.due_date) === 'expired'}>
                {getDaysClass(a.due_date) === 'expired' ? 'Expiré' : '📤 Soumettre'}
              </button>
            </div>
          {/each}
        {/if}

      {:else if activeTab === 'courses'}
        <div class="page-header">
          <div>
            <div class="page-title">Mes Cours</div>
            <div class="page-sub">{courses.length} cours disponible(s)</div>
          </div>
        </div>

        <div class="stats">
          <div class="stat"><div class="stat-num">{courses.length}</div><div class="stat-label">Total</div></div>
          <div class="stat"><div class="stat-num">{courses.reduce((s, c) => s + (c.lessons || 0), 0)}</div><div class="stat-label">Leçons</div></div>
          <div class="stat"><div class="stat-num">{courses.reduce((s, c) => s + (c.duration || 0), 0)}h</div><div class="stat-label">Durée totale</div></div>
          <div class="stat"><div class="stat-num">{courses.filter(c => c.active !== false).length}</div><div class="stat-label">Actifs</div></div>
        </div>

        {#if courses.length === 0}
          <div class="empty">📚<br>Aucun cours disponible.<br>Demandez à votre professeur de rejoindre une classe !</div>
        {:else}
          {#each courses as c}
            <div class="ccard">
              <div class="cicon">
                {#if c.module === 'Généralités sur les systèmes informatiques' || c.subject === 'Généralités sur les systèmes informatiques'}🖥️
                {:else if c.module === "Logiciels (Système d'exploitation et Bureautique)" || c.subject === "Logiciels (Système d'exploitation et Bureautique)"}⚙️
                {:else if c.module === 'Algorithmique et Programmation' || c.subject === 'Algorithmique et Programmation'}🧩
                {:else if c.module === 'Réseaux informatiques et Internet' || c.subject === 'Réseaux informatiques et Internet'}🌐
                {:else}📚{/if}
              </div>
              <div class="ainfo">
                <div class="atitle">{c.title || c.course_title || c.name}</div>
                {#if c.description}<div style="font-size:0.8rem;color:#4a7fa8;margin:0.2rem 0">{c.description}</div>{/if}
                <div style="margin-top:0.35rem">
                  {#if c.module}<span class="ctag" style="background:#1e293b;color:#3b82f6;border:1px solid #3b82f6;">📁 {c.module}</span>
                  {:else if c.subject}<span class="ctag">📘 {c.subject}</span>{/if}
                  <span class="ctag">🎓 {c.level || 'Débutant'}</span>
                  <span class="ctag">📖 {c.lessons || 0} leçons</span>
                  <span class="ctag">⏱️ {c.duration || 0}h</span>
                </div>
                {#if c.progress !== undefined}
                  <div style="margin-top:0.5rem;font-size:0.72rem;color:#2a5f8f">Progression : {c.progress}%</div>
                  <div class="progress-wrap"><div class="progress-bar" style="width:{c.progress}%"></div></div>
                {/if}
                {#if c.pdfs && c.pdfs.length > 0}
                  <div class="pdf-list">
                    <div style="font-size:0.75rem;color:#2a5f8f;margin-top:0.6rem;margin-bottom:0.2rem;text-transform:uppercase;letter-spacing:0.5px;">📎 Documents du cours</div>
                    {#each c.pdfs as pdf}
                      <div class="pdf-item">
                        <span class="pdf-name">📄 {pdf.title || pdf.filename || 'Document'}</span>
                        <div class="pdf-actions">
                          <button class="btn-pdf" on:click={() => openPdf(`${API}${pdf.url}`, pdf.title || pdf.filename)}>👁 Lire</button>
                          <button class="btn-dl" on:click={() => downloadPdf(`${API}${pdf.url}`, pdf.filename || 'document.pdf')}>⬇ Télécharger</button>
                        </div>
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
              <span class="badge-active">Actif</span>
            </div>
          {/each}
        {/if}
      {/if}
    </main>
  </div>
</div>

{#if selectedPdf}
  <div class="pdf-modal-backdrop" on:click|self={closePdf}>
    <div class="pdf-modal">
      <div class="pdf-modal-header">
        <div class="pdf-modal-title">📄 {selectedPdf.title}</div>
        <div class="pdf-modal-actions">
          <button class="btn-dl" on:click={() => downloadPdf(selectedPdf.url, selectedPdf.title + '.pdf')}>⬇ Télécharger</button>
          <button class="btn-close" on:click={closePdf}>✕ Fermer</button>
        </div>
      </div>
      <iframe class="pdf-iframe" src="{selectedPdf.url}#toolbar=1&navpanes=0" title={selectedPdf.title}></iframe>
    </div>
  </div>
{/if}