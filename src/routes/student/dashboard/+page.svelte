<script lang="ts">
  import { goto } from '$app/navigation';
  import { user } from '$lib/stores';
  import { onMount, tick } from 'svelte';

  // ── State ─────────────────────────────────────────────────
  let loading = true;
  let activeTab = 'devoirs';
  let classrooms: any[] = [];
  let courses: any[]     = [];
  let assignments: any[] = [];
  let submissions: Record<string, any> = {};
  let submissionText = '';
  let submissionFile: File | null = null;
  let submitStatus = '';
  let showJoinModal = false;
  let joinCode = '';
  let joinLoading = false;
  let joinError = '';
  let joinSuccess = '';
  let selectedPdf: { url: string; title: string } | null = null;
  let selectedCourseForChat: any = null;
  let searchQuery = '';

  // Chat RAG
  let chatMessages: { role: string; content: string }[] = [];
  let chatInput = '';
  let chatLoading = false;
  let chatIngested = false;
  let checkingIngest = false;
  let chatContainer: HTMLElement;

  const API = 'http://localhost:8080';

  // ── Auth ──────────────────────────────────────────────────
  function getToken(): string | null {
    try {
      const t = localStorage.getItem('token') || sessionStorage.getItem('token');
      if (t) return t.replace(/^"|"$/g, '');
    } catch {}
    return null;
  }

  async function apiFetch(path: string, options: RequestInit = {}) {
    const t = getToken();
    const res = await fetch(`${API}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(t ? { Authorization: `Bearer ${t}` } : {}),
        ...(options.headers || {}),
      },
    });
    if (!res.ok) throw new Error(`${res.status}`);
    return res.json();
  }

  // ── Chargement ────────────────────────────────────────────
  async function loadAll() {
    loading = true;
    try { classrooms = await apiFetch('/api/v1/my-classrooms'); } catch { classrooms = []; }
    const allCourses: any[] = [];
    const allAssignments: any[] = [];
    for (const classroom of classrooms) {
      const code = classroom.class_code || classroom.code;
      if (!code) continue;
      try { const c = await apiFetch(`/api/v1/classroom/${code}/courses`); allCourses.push(...(Array.isArray(c) ? c : [])); } catch {}
      try { const a = await apiFetch(`/api/v1/classroom/${code}/assignments`); allAssignments.push(...(Array.isArray(a) ? a : [])); } catch {}
    }
    courses = allCourses;
    assignments = allAssignments;
    loading = false;
  }

  // ── Join ──────────────────────────────────────────────────
  async function joinClassroom() {
    if (!joinCode.trim()) { joinError = 'Veuillez entrer un code.'; return; }
    joinLoading = true; joinError = ''; joinSuccess = '';
    try {
      await apiFetch('/api/v1/join-classroom', { method: 'POST', body: JSON.stringify({ code: joinCode.trim().toUpperCase() }) });
      joinSuccess = 'Classe rejointe !';
      joinCode = '';
      await loadAll();
      setTimeout(() => { showJoinModal = false; joinSuccess = ''; }, 2000);
    } catch { joinError = 'Code invalide ou classe introuvable.'; }
    joinLoading = false;
  }

  // ── Soumission ────────────────────────────────────────────
  function handleSubmit(assignmentId: string) {
    if (!submissionText.trim() && !submissionFile) { submitStatus = 'error'; return; }
    submissions = { ...submissions, [assignmentId]: { text: submissionText, file: submissionFile?.name, date: new Date().toLocaleDateString('fr-FR') } };
    submitStatus = 'ok';
    submissionText = ''; submissionFile = null;
    setTimeout(() => submitStatus = '', 3000);
  }

  // ── RAG Chat ──────────────────────────────────────────────
  async function openCourseChat(course: any) {
    selectedCourseForChat = course;
    chatMessages = [{ role: 'assistant', content: `Bonjour ! Je suis Ada 🎓 Pose-moi une question sur le cours **${course.title}**.` }];
    chatInput = '';
    chatLoading = false;
    checkingIngest = true;
    try {
      const status = await apiFetch(`/api/v1/courses/${course.id}/ingest/status`);
      chatIngested = status.ingested;
      if (!chatIngested) {
        chatMessages = [...chatMessages, { role: 'assistant', content: '⚙️ Indexation du cours en cours, cela peut prendre quelques secondes...' }];
        await apiFetch(`/api/v1/courses/${course.id}/ingest`, { method: 'POST' });
        await new Promise(r => setTimeout(r, 3000));
        const s2 = await apiFetch(`/api/v1/courses/${course.id}/ingest/status`);
        chatIngested = s2.ingested;
        chatMessages = chatMessages.filter(m => !m.content.includes('Indexation'));
        if (chatIngested) chatMessages = [...chatMessages, { role: 'assistant', content: '✅ Cours indexé ! Pose ta question.' }];
      }
    } catch { chatIngested = false; }
    checkingIngest = false;
    await tick();
    scrollChat();
  }

  function closeCourseChat() { selectedCourseForChat = null; chatMessages = []; }

  async function sendChatMessage() {
    if (!chatInput.trim() || chatLoading) return;
    const question = chatInput.trim();
    chatInput = '';
    chatMessages = [...chatMessages, { role: 'user', content: question }];
    chatLoading = true;
    await tick(); scrollChat();
    try {
      const history = chatMessages.slice(0, -1).map(m => ({ role: m.role, content: m.content }));
      const res = await apiFetch(`/api/v1/courses/${selectedCourseForChat.id}/chat`, {
        method: 'POST',
        body: JSON.stringify({ question, history })
      });
      chatMessages = [...chatMessages, { role: 'assistant', content: res.answer }];
    } catch {
      chatMessages = [...chatMessages, { role: 'assistant', content: '❌ Erreur de connexion. Réessaie.' }];
    }
    chatLoading = false;
    await tick(); scrollChat();
  }

  function scrollChat() {
    if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;
  }

  // ── Utilitaires ───────────────────────────────────────────
  function formatDeadline(d: string) {
    const days = Math.ceil((new Date(d).getTime() - Date.now()) / 86400000);
    if (days < 0)   return { label: 'Expiré',          color: '#dc2626', bg: '#fef2f2', dot: '#fca5a5' };
    if (days === 0) return { label: "Aujourd'hui",       color: '#d97706', bg: '#fffbeb', dot: '#fcd34d' };
    if (days <= 3)  return { label: `${days}j`,          color: '#ea580c', bg: '#fff7ed', dot: '#fdba74' };
    return               { label: `${days} jours`,      color: '#16a34a', bg: '#f0fdf4', dot: '#86efac' };
  }

  function fileIcon(type: string): string {
    if (type === '.pdf') return '📄';
    if (['.doc','.docx'].includes(type)) return '📝';
    if (['.ppt','.pptx'].includes(type)) return '📊';
    return '📁';
  }

  function formatSize(bytes: number): string {
    if (!bytes) return '-';
    if (bytes < 1024) return bytes + ' o';
    if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' Ko';
    return (bytes/(1024*1024)).toFixed(1) + ' Mo';
  }

  function getCourseFileUrl(course: any): string {
    const t = getToken();
    return `${API}/api/v1/courses/${course.id}/file${t ? `?token=${t}` : ''}`;
  }

  async function downloadFile(url: string, filename: string) {
    const t = getToken();
    try {
      const res = await fetch(url, { headers: t ? { Authorization: `Bearer ${t}` } : {} });
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = filename || 'document'; a.click();
      URL.revokeObjectURL(a.href);
    } catch { window.open(url, '_blank'); }
  }

  async function openPdf(url: string, title: string) {
    const t = getToken();
    try {
      const res = await fetch(url, { headers: t ? { Authorization: `Bearer ${t}` } : {} });
      const blob = await res.blob();
      selectedPdf = { url: URL.createObjectURL(blob), title };
    } catch { window.open(url, '_blank'); }
  }

  function closePdf() { selectedPdf = null; }

  const COURSE_COLORS = [
    { bg: '#eff6ff', border: '#bfdbfe', icon: '#3b82f6', tag: '#1d4ed8' },
    { bg: '#f0fdf4', border: '#bbf7d0', icon: '#22c55e', tag: '#15803d' },
    { bg: '#fdf4ff', border: '#e9d5ff', icon: '#a855f7', tag: '#7e22ce' },
    { bg: '#fff7ed', border: '#fed7aa', icon: '#f97316', tag: '#c2410c' },
    { bg: '#fef2f2', border: '#fecaca', icon: '#ef4444', tag: '#b91c1c' },
    { bg: '#f0fdfa', border: '#99f6e4', icon: '#14b8a6', tag: '#0f766e' },
  ];

  function getCourseColor(i: number) { return COURSE_COLORS[i % COURSE_COLORS.length]; }

  $: filteredCourses = courses.filter(c => !searchQuery || c.title?.toLowerCase().includes(searchQuery.toLowerCase()));
  $: filteredAssignments = assignments.filter(a => !searchQuery || a.title?.toLowerCase().includes(searchQuery.toLowerCase()));
  $: totalAssignments = assignments.length;
  $: submittedCount = Object.keys(submissions).length;
  $: urgentCount = assignments.filter(a => { const d = Math.ceil((new Date(a.due_date).getTime()-Date.now())/86400000); return d>=0&&d<=3&&!submissions[a.id]; }).length;

  onMount(async () => {
    if (!$user) { goto('/auth'); return; }
    if ($user.role !== 'user') { goto(`/${$user.role}`); return; }
    await loadAll();
  });
</script>

<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=DM+Mono:wght@400;500&display=swap');

  :root {
    --bg: #f8fafc;
    --surface: #ffffff;
    --surface2: #f1f5f9;
    --border: #e2e8f0;
    --border2: #cbd5e1;
    --text: #0f172a;
    --text2: #475569;
    --text3: #94a3b8;
    --accent: #6366f1;
    --accent2: #818cf8;
    --accent-bg: #eef2ff;
    --green: #16a34a;
    --green-bg: #f0fdf4;
    --shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
    --shadow-md: 0 4px 12px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04);
    --shadow-lg: 0 12px 32px rgba(0,0,0,0.1), 0 4px 8px rgba(0,0,0,0.06);
    --radius: 12px;
    --radius-sm: 8px;
    --radius-lg: 16px;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  .app {
    min-height: 100vh;
    background: var(--bg);
    font-family: 'Plus Jakarta Sans', sans-serif;
    color: var(--text);
    display: flex;
  }

  /* ── SIDEBAR ── */
  .sidebar {
    width: 240px;
    background: var(--surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    position: fixed;
    top: 0; left: 0; bottom: 0;
    z-index: 20;
    box-shadow: var(--shadow);
  }

  .sidebar-logo {
    padding: 24px 20px 20px;
    display: flex;
    align-items: center;
    gap: 10px;
    border-bottom: 1px solid var(--border);
  }

  .logo-icon {
    width: 36px; height: 36px;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px;
    box-shadow: 0 2px 8px rgba(99,102,241,0.3);
  }

  .logo-text { font-size: 1rem; font-weight: 800; color: var(--text); letter-spacing: -0.3px; }
  .logo-text span { color: var(--accent); }

  .sidebar-nav { padding: 12px 10px; flex: 1; display: flex; flex-direction: column; gap: 2px; }

  .nav-section-title {
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text3);
    padding: 8px 10px 4px;
  }

  .nav-btn {
    display: flex; align-items: center; gap: 10px;
    padding: 9px 12px;
    border-radius: var(--radius-sm);
    cursor: pointer; font-size: 0.875rem; color: var(--text2);
    font-weight: 500; transition: all 0.15s;
    border: none; background: none; width: 100%;
    text-align: left; font-family: inherit;
  }

  .nav-btn:hover { background: var(--surface2); color: var(--text); }
  .nav-btn.active { background: var(--accent-bg); color: var(--accent); font-weight: 600; }
  .nav-btn .nav-icon { font-size: 1rem; width: 22px; text-align: center; flex-shrink: 0; }

  .nav-badge {
    margin-left: auto;
    background: var(--accent);
    color: white;
    font-size: 0.65rem;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 20px;
    min-width: 20px;
    text-align: center;
  }

  .nav-badge.urgent { background: #ef4444; }

  .nav-divider { height: 1px; background: var(--border); margin: 8px 10px; }

  .btn-join-nav {
    display: flex; align-items: center; gap: 10px;
    padding: 9px 12px; border-radius: var(--radius-sm);
    cursor: pointer; font-size: 0.875rem; color: var(--green);
    font-weight: 600; transition: all 0.15s;
    border: none; background: none; width: 100%;
    text-align: left; font-family: inherit;
  }
  .btn-join-nav:hover { background: var(--green-bg); }

  .sidebar-user {
    padding: 14px 16px;
    border-top: 1px solid var(--border);
    display: flex; align-items: center; gap: 10px;
  }

  .user-avatar {
    width: 34px; height: 34px; border-radius: 50%;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    display: flex; align-items: center; justify-content: center;
    font-size: 0.8rem; font-weight: 700; color: white; flex-shrink: 0;
  }

  .user-name { font-size: 0.8rem; font-weight: 600; color: var(--text); }
  .user-role { font-size: 0.7rem; color: var(--text3); }

  /* ── MAIN ── */
  .main { flex: 1; margin-left: 240px; display: flex; flex-direction: column; min-height: 100vh; }

  /* ── TOPBAR ── */
  .topbar {
    height: 58px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    display: flex; align-items: center; padding: 0 24px; gap: 14px;
    position: sticky; top: 0; z-index: 10;
    box-shadow: var(--shadow);
  }

  .topbar-title { font-size: 1rem; font-weight: 700; color: var(--text); flex: 1; }
  .topbar-sub { font-size: 0.75rem; color: var(--text3); font-weight: 400; margin-left: 8px; }

  .search-wrap { position: relative; width: 280px; }
  .search-icon { position: absolute; left: 11px; top: 50%; transform: translateY(-50%); color: var(--text3); font-size: 0.85rem; pointer-events: none; }
  .search-input {
    width: 100%; background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 7px 12px 7px 32px;
    font-size: 0.8rem; color: var(--text); outline: none; font-family: inherit;
    transition: all 0.15s;
  }
  .search-input:focus { border-color: var(--accent); background: white; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
  .search-input::placeholder { color: var(--text3); }

  .btn-primary-sm {
    padding: 7px 14px; border-radius: var(--radius-sm); border: none;
    background: var(--accent); color: white; font-size: 0.8rem; font-weight: 600;
    cursor: pointer; font-family: inherit; display: inline-flex; align-items: center; gap: 5px;
    transition: all 0.15s; white-space: nowrap;
    box-shadow: 0 2px 8px rgba(99,102,241,0.3);
  }
  .btn-primary-sm:hover { background: #4f46e5; transform: translateY(-1px); }

  /* ── CONTENT ── */
  .content { padding: 24px; flex: 1; }

  /* ── STATS ── */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin-bottom: 24px;
  }

  .stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px;
    display: flex; align-items: center; gap: 14px;
    box-shadow: var(--shadow);
    transition: all 0.2s;
  }

  .stat-card:hover { box-shadow: var(--shadow-md); transform: translateY(-1px); }

  .stat-icon {
    width: 44px; height: 44px; border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.2rem; flex-shrink: 0;
  }

  .stat-val { font-size: 1.5rem; font-weight: 800; color: var(--text); line-height: 1; }
  .stat-lbl { font-size: 0.72rem; color: var(--text3); margin-top: 3px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }

  /* ── TABS ── */
  .tabs-wrap {
    display: flex; gap: 0;
    border-bottom: 2px solid var(--border);
    margin-bottom: 20px;
  }

  .tab-btn {
    padding: 10px 20px; font-size: 0.875rem; font-weight: 500;
    color: var(--text3); cursor: pointer; border: none; background: none;
    font-family: inherit; border-bottom: 2px solid transparent;
    margin-bottom: -2px; transition: all 0.15s; display: flex; align-items: center; gap: 6px;
  }

  .tab-btn:hover { color: var(--text); }
  .tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }

  /* ── ASSIGNMENT LIST ── */
  .assignment-list { display: flex; flex-direction: column; gap: 10px; }

  .assignment-row {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px 18px;
    display: flex; align-items: center; gap: 14px;
    cursor: pointer; transition: all 0.15s;
    box-shadow: var(--shadow);
  }

  .assignment-row:hover { border-color: var(--accent2); box-shadow: var(--shadow-md); transform: translateY(-1px); }

  .arow-icon {
    width: 42px; height: 42px; border-radius: 11px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.1rem; flex-shrink: 0;
  }

  .arow-info { flex: 1; min-width: 0; }
  .arow-title { font-weight: 600; font-size: 0.9rem; color: var(--text); margin-bottom: 4px; }
  .arow-meta { font-size: 0.75rem; color: var(--text3); display: flex; gap: 12px; flex-wrap: wrap; }

  .deadline-pill {
    font-size: 0.72rem; font-weight: 700;
    padding: 3px 10px; border-radius: 20px;
    white-space: nowrap; flex-shrink: 0;
    display: flex; align-items: center; gap: 5px;
  }

  .deadline-dot { width: 6px; height: 6px; border-radius: 50%; }

  .btn-soumettre {
    padding: 6px 14px; border-radius: var(--radius-sm);
    border: 1.5px solid var(--border2); background: var(--surface);
    color: var(--accent); font-size: 0.78rem; font-weight: 600;
    cursor: pointer; font-family: inherit; transition: all 0.15s;
    white-space: nowrap; flex-shrink: 0;
  }
  .btn-soumettre:hover:not(:disabled) { background: var(--accent-bg); border-color: var(--accent); }
  .btn-soumettre:disabled { color: var(--text3); cursor: not-allowed; border-color: var(--border); }

  /* ── COURSE GRID ── */
  .course-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }

  .course-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    overflow: hidden;
    box-shadow: var(--shadow);
    transition: all 0.2s;
    display: flex; flex-direction: column;
  }

  .course-card:hover { box-shadow: var(--shadow-lg); transform: translateY(-2px); }

  .course-card-header {
    padding: 20px;
    position: relative;
  }

  .course-tag {
    font-size: 0.65rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.8px; margin-bottom: 8px; display: block;
  }

  .course-title { font-size: 1rem; font-weight: 700; color: var(--text); line-height: 1.4; }
  .course-emoji { position: absolute; top: 16px; right: 16px; font-size: 1.6rem; opacity: 0.7; }

  .course-card-body { padding: 0 20px 16px; flex: 1; display: flex; flex-direction: column; gap: 10px; }

  .course-desc {
    font-size: 0.8rem; color: var(--text2); line-height: 1.5;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }

  .course-meta-row { display: flex; align-items: center; gap: 8px; font-size: 0.72rem; color: var(--text3); }

  .course-actions { display: flex; gap: 6px; margin-top: auto; }

  .btn-read {
    flex: 1; padding: 7px 12px; border-radius: var(--radius-sm); border: none;
    font-size: 0.78rem; font-weight: 600; cursor: pointer; font-family: inherit;
    transition: all 0.15s; display: flex; align-items: center; justify-content: center; gap: 5px;
  }

  .btn-dl {
    padding: 7px 10px; border-radius: var(--radius-sm);
    border: 1px solid var(--border); background: var(--surface2);
    color: var(--text2); font-size: 0.78rem; cursor: pointer;
    font-family: inherit; transition: all 0.15s;
  }
  .btn-dl:hover { background: var(--surface); border-color: var(--border2); }

  .btn-chat {
    padding: 7px 10px; border-radius: var(--radius-sm);
    border: 1px solid #e9d5ff; background: #fdf4ff;
    color: #7e22ce; font-size: 0.78rem; cursor: pointer;
    font-family: inherit; transition: all 0.15s; font-weight: 600;
  }
  .btn-chat:hover { background: #f5f3ff; border-color: #c4b5fd; }

  /* ── EMPTY ── */
  .empty {
    text-align: center; padding: 60px 20px;
    display: flex; flex-direction: column; align-items: center; gap: 12px;
  }
  .empty-icon { font-size: 3.5rem; }
  .empty-title { font-size: 1rem; font-weight: 700; color: var(--text); }
  .empty-sub { font-size: 0.875rem; color: var(--text3); max-width: 320px; line-height: 1.6; }

  /* ── BANNER ── */
  .banner-warn {
    background: #fffbeb; border: 1px solid #fde68a;
    border-left: 4px solid #f59e0b; border-radius: var(--radius-sm);
    padding: 12px 16px; margin-bottom: 20px;
    font-size: 0.875rem; color: #92400e;
    display: flex; align-items: center; gap: 8px;
  }

  .spin { display: flex; align-items: center; justify-content: center; height: 300px; gap: 10px; color: var(--text3); }
  .spinner { width: 24px; height: 24px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── MODAL JOIN ── */
  .overlay { position: fixed; inset: 0; background: rgba(15,23,42,0.5); backdrop-filter: blur(4px); z-index: 999; display: flex; align-items: center; justify-content: center; }

  .modal {
    background: var(--surface);
    border-radius: var(--radius-lg);
    padding: 32px;
    width: 420px; max-width: 95vw;
    box-shadow: var(--shadow-lg);
    border: 1px solid var(--border);
  }

  .modal-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
  .modal-icon { width: 42px; height: 42px; border-radius: 11px; background: var(--accent-bg); display: flex; align-items: center; justify-content: center; font-size: 1.2rem; }
  .modal-title { font-size: 1.1rem; font-weight: 700; color: var(--text); }
  .modal-sub { font-size: 0.875rem; color: var(--text3); margin-bottom: 20px; }

  .code-input {
    width: 100%; background: var(--surface2); border: 1.5px solid var(--border);
    border-radius: var(--radius-sm); padding: 14px 16px;
    font-size: 1.5rem; font-weight: 800; color: var(--accent); font-family: 'DM Mono', monospace;
    text-align: center; letter-spacing: 6px; text-transform: uppercase; outline: none;
    transition: all 0.2s;
  }
  .code-input:focus { border-color: var(--accent); background: white; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
  .code-input.err { border-color: #ef4444; }

  .msg-error { color: #dc2626; font-size: 0.8rem; margin-top: 8px; display: flex; align-items: center; gap: 5px; }
  .msg-success { color: var(--green); font-size: 0.8rem; margin-top: 8px; }

  .modal-actions { display: flex; gap: 10px; margin-top: 20px; }
  .btn-cancel { flex: 1; padding: 10px; border-radius: var(--radius-sm); border: 1.5px solid var(--border); background: var(--surface2); color: var(--text2); cursor: pointer; font-size: 0.875rem; font-weight: 500; font-family: inherit; transition: all 0.15s; }
  .btn-cancel:hover { background: var(--surface); }
  .btn-confirm { flex: 1; padding: 10px; border-radius: var(--radius-sm); border: none; background: var(--accent); color: white; cursor: pointer; font-size: 0.875rem; font-weight: 600; font-family: inherit; transition: all 0.15s; box-shadow: 0 2px 8px rgba(99,102,241,0.3); }
  .btn-confirm:hover:not(:disabled) { background: #4f46e5; }
  .btn-confirm:disabled { background: var(--accent2); cursor: not-allowed; }

  /* ── PDF VIEWER ── */
  .pdf-backdrop { position: fixed; inset: 0; background: rgba(15,23,42,0.9); z-index: 999; display: flex; flex-direction: column; align-items: center; padding: 20px; }
  .pdf-shell { width: 100%; max-width: 960px; height: calc(100vh - 40px); display: flex; flex-direction: column; background: white; border-radius: var(--radius-lg); overflow: hidden; box-shadow: var(--shadow-lg); }
  .pdf-topbar { display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; background: var(--surface); border-bottom: 1px solid var(--border); flex-shrink: 0; }
  .pdf-title { font-size: 0.9rem; font-weight: 600; color: var(--text); display: flex; align-items: center; gap: 8px; }
  .pdf-actions { display: flex; gap: 8px; }
  .pdf-iframe { flex: 1; width: 100%; border: none; }
  .btn-close { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; border-radius: var(--radius-sm); padding: 5px 12px; font-size: 0.8rem; font-weight: 600; cursor: pointer; font-family: inherit; transition: all 0.15s; }
  .btn-close:hover { background: #fee2e2; }

  /* ── CHAT PANEL ── */
  .chat-panel-backdrop { position: fixed; inset: 0; background: rgba(15,23,42,0.5); backdrop-filter: blur(4px); z-index: 999; display: flex; align-items: stretch; justify-content: flex-end; }

  .chat-panel {
    width: 400px; max-width: 95vw;
    background: var(--surface);
    display: flex; flex-direction: column;
    box-shadow: -8px 0 32px rgba(0,0,0,0.15);
    animation: slideIn 0.25s ease;
  }

  @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }

  .chat-header {
    padding: 18px 20px;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    display: flex; align-items: center; gap: 12px; flex-shrink: 0;
  }

  .chat-avatar {
    width: 40px; height: 40px; border-radius: 50%;
    background: rgba(255,255,255,0.2);
    display: flex; align-items: center; justify-content: center;
    font-size: 1.2rem; flex-shrink: 0;
  }

  .chat-header-info { flex: 1; min-width: 0; }
  .chat-header-name { font-size: 0.9rem; font-weight: 700; color: white; }
  .chat-header-course { font-size: 0.72rem; color: rgba(255,255,255,0.75); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chat-close { background: rgba(255,255,255,0.15); border: none; color: white; border-radius: 8px; width: 30px; height: 30px; cursor: pointer; font-size: 1rem; display: flex; align-items: center; justify-content: center; transition: all 0.15s; }
  .chat-close:hover { background: rgba(255,255,255,0.25); }

  .chat-messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; background: #fafafa; }

  .chat-msg { display: flex; flex-direction: column; max-width: 88%; }
  .chat-msg.user { align-self: flex-end; align-items: flex-end; }
  .chat-msg.assistant { align-self: flex-start; align-items: flex-start; }

  .chat-msg-label { font-size: 0.65rem; color: var(--text3); margin-bottom: 4px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }

  .chat-bubble {
    padding: 10px 14px; border-radius: 14px;
    font-size: 0.85rem; line-height: 1.55;
    white-space: pre-wrap; word-break: break-word;
  }

  .chat-msg.user .chat-bubble { background: linear-gradient(135deg, #6366f1, #8b5cf6); color: white; border-bottom-right-radius: 4px; }
  .chat-msg.assistant .chat-bubble { background: white; color: var(--text); border: 1px solid var(--border); border-bottom-left-radius: 4px; box-shadow: var(--shadow); }

  .chat-typing { display: flex; gap: 4px; padding: 12px 14px; background: white; border: 1px solid var(--border); border-radius: 14px; border-bottom-left-radius: 4px; width: fit-content; box-shadow: var(--shadow); }
  .typing-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--text3); animation: typing 1.2s ease-in-out infinite; }
  .typing-dot:nth-child(2) { animation-delay: 0.2s; }
  .typing-dot:nth-child(3) { animation-delay: 0.4s; }
  @keyframes typing { 0%,60%,100% { transform: translateY(0); opacity: 0.4; } 30% { transform: translateY(-6px); opacity: 1; } }

  .chat-input-wrap {
    padding: 14px 16px;
    background: var(--surface);
    border-top: 1px solid var(--border);
    display: flex; gap: 8px; align-items: flex-end;
    flex-shrink: 0;
  }

  .chat-textarea {
    flex: 1; background: var(--surface2); border: 1.5px solid var(--border);
    border-radius: 10px; padding: 9px 12px;
    font-size: 0.85rem; color: var(--text); resize: none;
    font-family: inherit; outline: none; transition: all 0.15s;
    min-height: 40px; max-height: 100px; line-height: 1.4;
  }
  .chat-textarea:focus { border-color: var(--accent); background: white; }
  .chat-textarea::placeholder { color: var(--text3); }

  .btn-send {
    width: 38px; height: 38px; border-radius: 10px; border: none;
    background: var(--accent); color: white; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    font-size: 1rem; transition: all 0.15s; flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(99,102,241,0.3);
  }
  .btn-send:hover:not(:disabled) { background: #4f46e5; transform: scale(1.05); }
  .btn-send:disabled { background: var(--border2); cursor: not-allowed; box-shadow: none; }

  /* ── SUBMISSION ── */
  .sub-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 14px; box-shadow: var(--shadow); }
  .sub-textarea { width: 100%; min-height: 140px; padding: 12px 14px; border-radius: var(--radius-sm); border: 1.5px solid var(--border); background: var(--surface2); color: var(--text); font-size: 0.875rem; resize: vertical; box-sizing: border-box; font-family: inherit; line-height: 1.6; outline: none; transition: all 0.15s; }
  .sub-textarea:focus { border-color: var(--accent); background: white; }

  .btn { padding: 7px 16px; border-radius: var(--radius-sm); border: 1.5px solid var(--border2); background: var(--surface2); color: var(--text); cursor: pointer; font-size: 0.875rem; font-weight: 500; font-family: inherit; display: inline-flex; align-items: center; gap: 6px; transition: all 0.15s; }
  .btn:hover { background: var(--surface); }
  .btn-primary { padding: 8px 18px; border-radius: var(--radius-sm); border: none; background: var(--accent); color: white; cursor: pointer; font-size: 0.875rem; font-weight: 600; font-family: inherit; display: inline-flex; align-items: center; gap: 6px; transition: all 0.15s; box-shadow: 0 2px 8px rgba(99,102,241,0.25); }
  .btn-primary:hover { background: #4f46e5; }

  @media (max-width: 768px) {
    .sidebar { transform: translateX(-100%); }
    .main { margin-left: 0; }
    .stats-grid { grid-template-columns: repeat(2,1fr); }
    .course-grid { grid-template-columns: 1fr; }
    .chat-panel { width: 100%; }
  }
</style>

<div class="app">

  <!-- ── SIDEBAR ── -->
  <aside class="sidebar">
    <div class="sidebar-logo">
      <div class="logo-icon">🎓</div>
      <div class="logo-text">Open<span>TutorAI</span></div>
    </div>

    <nav class="sidebar-nav">
      <div class="nav-section-title">Navigation</div>

      <button class="nav-btn {activeTab === 'devoirs' ? 'active' : ''}" on:click={() => activeTab = 'devoirs'}>
        <span class="nav-icon">📋</span>
        Mes Devoirs
        {#if urgentCount > 0}<span class="nav-badge urgent">{urgentCount}</span>{/if}
      </button>

      <button class="nav-btn {activeTab === 'cours' ? 'active' : ''}" on:click={() => activeTab = 'cours'}>
        <span class="nav-icon">📚</span>
        Mes Cours
        {#if courses.length > 0}<span class="nav-badge">{courses.length}</span>{/if}
      </button>

      <div class="nav-divider"></div>

      <button class="btn-join-nav" on:click={() => showJoinModal = true}>
        <span class="nav-icon">➕</span>
        Rejoindre une classe
      </button>
    </nav>

    {#if $user}
      <div class="sidebar-user">
        <div class="user-avatar">{$user.name?.charAt(0)?.toUpperCase() ?? 'E'}</div>
        <div>
          <div class="user-name">{$user.name}</div>
          <div class="user-role">Étudiant</div>
        </div>
      </div>
    {/if}
  </aside>

  <!-- ── MAIN ── -->
  <div class="main">

    <!-- Topbar -->
    <div class="topbar">
      <div class="topbar-title">
        {activeTab === 'cours' ? 'Mes Cours' : 'Mes Devoirs'}
        <span class="topbar-sub">
          {activeTab === 'cours' ? `${filteredCourses.length} cours` : `${filteredAssignments.length} devoirs`}
        </span>
      </div>

      <div class="search-wrap">
        <span class="search-icon">🔍</span>
        <input class="search-input" type="text" placeholder="Rechercher..." bind:value={searchQuery} />
      </div>

      <button class="btn-primary-sm" on:click={() => showJoinModal = true}>
        + Rejoindre une classe
      </button>
    </div>

    <!-- Content -->
    <div class="content">

      {#if loading}
        <div class="spin">
          <div class="spinner"></div>
          Chargement...
        </div>

      {:else}

        <!-- Stats -->
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-icon" style="background:#eff6ff">📚</div>
            <div>
              <div class="stat-val">{courses.length}</div>
              <div class="stat-lbl">Cours</div>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-icon" style="background:#f0fdf4">📋</div>
            <div>
              <div class="stat-val">{totalAssignments}</div>
              <div class="stat-lbl">Devoirs</div>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-icon" style="background:#fdf4ff">✅</div>
            <div>
              <div class="stat-val">{submittedCount}</div>
              <div class="stat-lbl">Soumis</div>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-icon" style="background:#fff7ed">⚡</div>
            <div>
              <div class="stat-val" style="color:{urgentCount > 0 ? '#ea580c' : 'var(--text)'}">{urgentCount}</div>
              <div class="stat-lbl">Urgents</div>
            </div>
          </div>
        </div>

        {#if classrooms.length === 0}
          <div class="banner-warn">
            ⚠️ Rejoignez une classe pour voir vos cours et devoirs.
            <button class="btn-primary-sm" style="margin-left:auto" on:click={() => showJoinModal = true}>Rejoindre</button>
          </div>
        {/if}

        <!-- Tabs -->
        <div class="tabs-wrap">
          <button class="tab-btn {activeTab === 'devoirs' ? 'active' : ''}" on:click={() => activeTab = 'devoirs'}>
            📋 Devoirs
            {#if totalAssignments > 0}<span style="background:var(--surface2);color:var(--text3);font-size:0.7rem;padding:2px 7px;border-radius:20px;font-weight:600">{totalAssignments}</span>{/if}
          </button>
          <button class="tab-btn {activeTab === 'cours' ? 'active' : ''}" on:click={() => activeTab = 'cours'}>
            📚 Cours
            {#if courses.length > 0}<span style="background:var(--surface2);color:var(--text3);font-size:0.7rem;padding:2px 7px;border-radius:20px;font-weight:600">{courses.length}</span>{/if}
          </button>
        </div>

        <!-- ── DEVOIRS ── -->
        {#if activeTab === 'devoirs'}
          {#if filteredAssignments.length === 0}
            <div class="empty">
              <div class="empty-icon">📋</div>
              <div class="empty-title">Aucun devoir disponible</div>
              <div class="empty-sub">{classrooms.length === 0 ? 'Rejoignez une classe pour voir vos devoirs.' : 'Votre professeur n\'a pas encore créé de devoirs.'}</div>
            </div>
          {:else}
            <div class="assignment-list">
              {#each filteredAssignments as a}
                {@const d = formatDeadline(a.due_date)}
                {@const sub = submissions[a.id]}
                <div class="assignment-row" on:click={() => { selectedCourseForChat = null; activeTab = 'devoir-detail'; }} role="button" tabindex="0">
                  <div class="arow-icon" style="background:{sub ? '#f0fdf4' : '#eff6ff'}">
                    {sub ? '✅' : '📋'}
                  </div>
                  <div class="arow-info">
                    <div class="arow-title">{a.title}</div>
                    <div class="arow-meta">
                      <span>📅 {a.due_date}{a.due_time ? ' à ' + a.due_time : ''}</span>
                      {#if a.course}<span>📚 {a.course}</span>{/if}
                      {#if a.points}<span>⭐ {a.points} pts</span>{/if}
                    </div>
                  </div>
                  {#if sub}
                    <span class="deadline-pill" style="background:#f0fdf4;color:#16a34a">
                      <span class="deadline-dot" style="background:#86efac"></span> Soumis
                    </span>
                  {:else}
                    <span class="deadline-pill" style="background:{d.bg};color:{d.color}">
                      <span class="deadline-dot" style="background:{d.dot}"></span>
                      {d.label}
                    </span>
                  {/if}
                  <button class="btn-soumettre" disabled={d.color === '#dc2626' && !sub}
                    on:click|stopPropagation={() => {
                      const modal = document.getElementById(`sub-${a.id}`);
                      if (modal) modal.style.display = modal.style.display === 'block' ? 'none' : 'block';
                    }}>
                    {d.color === '#dc2626' && !sub ? 'Expiré' : sub ? 'Voir' : 'Soumettre'}
                  </button>
                </div>

                <!-- Inline submission form -->
                <div id="sub-{a.id}" style="display:none;padding:0 0 10px 56px">
                  {#if submissions[a.id]}
                    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:14px 16px;font-size:0.85rem">
                      <div style="color:#16a34a;font-weight:600;margin-bottom:6px">✅ Soumis le {submissions[a.id].date}</div>
                      {#if submissions[a.id].text}<div style="color:var(--text2)">{submissions[a.id].text}</div>{/if}
                      {#if submissions[a.id].file}<div style="color:var(--text3);margin-top:4px">📎 {submissions[a.id].file}</div>{/if}
                    </div>
                  {:else}
                    <div class="sub-card" style="margin-bottom:0">
                      <textarea class="sub-textarea" bind:value={submissionText} placeholder="Rédigez votre réponse..."></textarea>
                      <div style="display:flex;align-items:center;gap:8px;margin-top:10px;flex-wrap:wrap">
                        <label class="btn" style="cursor:pointer;font-size:0.8rem">
                          📎 {submissionFile ? submissionFile.name : 'Joindre un fichier'}
                          <input type="file" style="display:none" on:change={e => submissionFile = e.target.files[0]} />
                        </label>
                        <div style="flex:1"></div>
                        <button class="btn-primary" style="font-size:0.8rem" on:click={() => handleSubmit(a.id)}>Soumettre</button>
                      </div>
                      {#if submitStatus === 'error'}<p style="color:#dc2626;font-size:0.78rem;margin-top:8px">⚠ Veuillez écrire une réponse ou joindre un fichier.</p>{/if}
                      {#if submitStatus === 'ok'}<p style="color:#16a34a;font-size:0.78rem;margin-top:8px">✓ Soumis avec succès !</p>{/if}
                    </div>
                  {/if}
                </div>
              {/each}
            </div>
          {/if}

        <!-- ── COURS ── -->
        {:else if activeTab === 'cours'}
          {#if filteredCourses.length === 0}
            <div class="empty">
              <div class="empty-icon">📚</div>
              <div class="empty-title">Aucun cours disponible</div>
              <div class="empty-sub">{classrooms.length === 0 ? 'Rejoignez une classe pour voir vos cours.' : 'Votre professeur n\'a pas encore uploadé de cours.'}</div>
            </div>
          {:else}
            <div class="course-grid">
              {#each filteredCourses as c, i}
                {@const col = getCourseColor(i)}
                <div class="course-card">
                  <div class="course-card-header" style="background:{col.bg};border-bottom:1px solid {col.border}">
                    <span class="course-tag" style="color:{col.tag}">{c.module || 'Cours'}</span>
                    <div class="course-title">{c.title}</div>
                    <div class="course-emoji">{fileIcon(c.file_type)}</div>
                  </div>
                  <div class="course-card-body">
                    {#if c.description}
                      <div class="course-desc">{c.description}</div>
                    {/if}
                    <div class="course-meta-row">
                      <span>📦 {formatSize(c.file_size)}</span>
                      <span>·</span>
                      <span>👤 {c.teacher_name || 'Enseignant'}</span>
                      <span>·</span>
                      <span style="font-family:'DM Mono',monospace;font-size:0.68rem;background:var(--surface2);padding:2px 6px;border-radius:4px;color:var(--text3)">{c.file_type?.replace('.','').toUpperCase()}</span>
                    </div>
                    <div class="course-actions">
                      {#if c.file_type === '.pdf'}
                        <button class="btn-read" style="background:{col.tag};color:white" on:click={() => openPdf(getCourseFileUrl(c), c.title)}>
                          👁 Lire
                        </button>
                      {/if}
                      <button class="btn-dl" on:click={() => downloadFile(getCourseFileUrl(c), c.original_filename || c.title)}>⬇</button>
                      <button class="btn-chat" on:click={() => openCourseChat(c)}>🤖 Ada</button>
                    </div>
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        {/if}

      {/if}
    </div>
  </div>
</div>

<!-- ── MODAL REJOINDRE ── -->
{#if showJoinModal}
  <div class="overlay" on:click|self={() => { showJoinModal = false; joinError = ''; joinCode = ''; }}>
    <div class="modal">
      <div class="modal-header">
        <div class="modal-icon">🏫</div>
        <div class="modal-title">Rejoindre une classe</div>
      </div>
      <p class="modal-sub">Entrez le code donné par votre professeur</p>
      <input class="code-input {joinError ? 'err' : ''}" type="text" bind:value={joinCode} placeholder="AB3K9Z" maxlength="10" on:keydown={(e) => e.key === 'Enter' && joinClassroom()} />
      {#if joinError}<p class="msg-error">❌ {joinError}</p>{/if}
      {#if joinSuccess}<p class="msg-success">✅ {joinSuccess}</p>{/if}
      <div class="modal-actions">
        <button class="btn-cancel" on:click={() => { showJoinModal = false; joinError = ''; joinCode = ''; }}>Annuler</button>
        <button class="btn-confirm" on:click={joinClassroom} disabled={joinLoading}>{joinLoading ? '⏳' : 'Rejoindre'}</button>
      </div>
    </div>
  </div>
{/if}

<!-- ── PDF VIEWER ── -->
{#if selectedPdf}
  <div class="pdf-backdrop" on:click|self={closePdf}>
    <div class="pdf-shell">
      <div class="pdf-topbar">
        <div class="pdf-title">📄 {selectedPdf.title}</div>
        <div class="pdf-actions">
          <button class="btn" style="font-size:0.78rem" on:click={() => downloadFile(selectedPdf.url, selectedPdf.title + '.pdf')}>⬇ Télécharger</button>
          <button class="btn-close" on:click={closePdf}>✕ Fermer</button>
        </div>
      </div>
      <iframe class="pdf-iframe" src="{selectedPdf.url}" title={selectedPdf.title}></iframe>
    </div>
  </div>
{/if}

<!-- ── CHAT RAG PANEL ── -->
{#if selectedCourseForChat}
  <div class="chat-panel-backdrop" on:click|self={closeCourseChat}>
    <div class="chat-panel">
      <div class="chat-header">
        <div class="chat-avatar">🤖</div>
        <div class="chat-header-info">
          <div class="chat-header-name">Ada · Tuteur IA</div>
          <div class="chat-header-course">{selectedCourseForChat.title}</div>
        </div>
        <button class="chat-close" on:click={closeCourseChat}>✕</button>
      </div>

      <div class="chat-messages" bind:this={chatContainer}>
        {#each chatMessages as msg}
          <div class="chat-msg {msg.role}">
            {#if msg.role === 'assistant'}<div class="chat-msg-label">Ada</div>{/if}
            <div class="chat-bubble">{msg.content}</div>
          </div>
        {/each}
        {#if chatLoading}
          <div class="chat-msg assistant">
            <div class="chat-msg-label">Ada</div>
            <div class="chat-typing">
              <div class="typing-dot"></div>
              <div class="typing-dot"></div>
              <div class="typing-dot"></div>
            </div>
          </div>
        {/if}
      </div>

      <div class="chat-input-wrap">
        <textarea class="chat-textarea" bind:value={chatInput} placeholder="Pose ta question..." rows="1"
          on:keydown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChatMessage(); } }}
        ></textarea>
        <button class="btn-send" on:click={sendChatMessage} disabled={!chatInput.trim() || chatLoading || checkingIngest}>→</button>
      </div>
    </div>
  </div>
{/if}