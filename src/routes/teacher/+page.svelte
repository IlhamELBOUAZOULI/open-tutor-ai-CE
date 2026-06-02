<script>
  import { goto } from '$app/navigation';
  import { user } from '$lib/stores';
  import { onMount, getContext } from 'svelte';

  // ── State ─────────────────────────────────────────────────────────────────
  let indexingCourseId = null;
  let indexedCourses = {};
  let generatingQuiz = {};
  let currentQuiz = null;
  let showQuizModal = false;

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
    'Généralités sur les systèmes informatiques','Logiciels',
    "Représentation de l'information",'Algorithmique et programmation',
    'Réseaux informatiques','Bases de données',"Systèmes d'exploitation",
    'Sécurité informatique','Internet et Web','Autre',
  ];

  const i18n = getContext('i18n');
  const API = '';

  // ── Auth ───────────────────────────────────────────────────────────────────
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
      headers: { ...(t ? { Authorization: `Bearer ${t}` } : {}), ...(options.headers || {}) }
    });
    if (!res.ok) throw new Error(`${res.status}`);
    return res.json();
  }

  // ── Load ───────────────────────────────────────────────────────────────────
  async function loadAll() {
    try { assignments = await apiFetch('/api/v1/assignments'); } catch { assignments = []; }
    try { students = await apiFetch('/api/v1/students'); } catch { students = []; }
    try { classroom = await apiFetch('/api/v1/classroom'); } catch { classroom = null; }
    try { courses = await apiFetch('/api/v1/courses'); } catch { courses = []; }
    await checkAllIndexed();
    loading = false;
  }

  // ── RAG / Index ────────────────────────────────────────────────────────────
  async function checkAllIndexed() {
    for (const c of courses) {
      try {
        const t = getToken();
        const res = await fetch(`${API}/api/v1/courses/${c.id}/ingest/status`, {
          headers: t ? { Authorization: `Bearer ${t}` } : {}
        });
        const data = await res.json();
        indexedCourses[c.id] = data.ingested;
      } catch { indexedCourses[c.id] = false; }
    }
    indexedCourses = { ...indexedCourses };
  }

  async function indexCourse(courseId) {
    if (indexingCourseId) return;
    indexingCourseId = courseId;
    try {
      const t = getToken();
      const res = await fetch(`${API}/api/v1/courses/${courseId}/ingest`, {
        method: 'POST',
        headers: t ? { Authorization: `Bearer ${t}` } : {}
      });
      if (!res.ok) throw new Error(await res.text());
      showSuccess('Indexation démarrée ! Patientez 30-60 secondes...');
      let attempts = 0;
      const check = setInterval(async () => {
        attempts++;
        try {
          const r = await fetch(`${API}/api/v1/courses/${courseId}/ingest/status`, {
            headers: t ? { Authorization: `Bearer ${t}` } : {}
          });
          const data = await r.json();
          if (data.ingested) {
            indexedCourses = { ...indexedCourses, [courseId]: true };
            indexingCourseId = null;
            clearInterval(check);
            showSuccess('Cours indexé ! Les étudiants peuvent poser des questions.');
          }
        } catch {}
        if (attempts > 24) { clearInterval(check); indexingCourseId = null; }
      }, 5000);
    } catch(e) {
      alert('Erreur: ' + e.message);
      indexingCourseId = null;
    }
  }

  // ── Quiz Generator ─────────────────────────────────────────────────────────
  async function generateQuiz(course) {
    if (!indexedCourses[course.id]) {
      alert('Ce cours doit être indexé avant de générer un QCM. Cliquez sur "Indexer" d\'abord.');
      return;
    }
    generatingQuiz = { ...generatingQuiz, [course.id]: true };
    try {
      const t = getToken();
      // Appel au endpoint RAG chat pour générer le QCM
      const res = await fetch(`${API}/api/v1/courses/${course.id}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(t ? { Authorization: `Bearer ${t}` } : {})
        },
        body: JSON.stringify({
          question: `Génère exactement 10 questions QCM à partir de ce cours. 
Pour chaque question, utilise ce format JSON strict:
{
  "questions": [
    {
      "question": "texte de la question",
      "options": ["A) option1", "B) option2", "C) option3", "D) option4"],
      "correct": "A",
      "explanation": "explication courte"
    }
  ]
}
Réponds UNIQUEMENT avec le JSON, sans texte avant ou après.`,
          history: []
        })
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();

      // Parser la réponse JSON du LLM
      let quizData;
      try {
        const answer = data.answer;
        const jsonMatch = answer.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          quizData = JSON.parse(jsonMatch[0]);
        } else {
          throw new Error('Format JSON invalide');
        }
      } catch(parseErr) {
        // Fallback: créer des questions basiques si le parsing échoue
        quizData = {
          questions: [{
            question: "Le cours a été analysé mais le format QCM n'a pas pu être généré. Essayez avec un cours plus détaillé.",
            options: ["A) Oui", "B) Non", "C) Peut-être", "D) Je ne sais pas"],
            correct: "A",
            explanation: "Réponse par défaut"
          }]
        };
      }

      currentQuiz = { ...quizData, courseTitle: course.title, courseId: course.id };
      showQuizModal = true;
      showSuccess('QCM généré avec succès !');
    } catch(e) {
      alert('Erreur génération QCM: ' + e.message);
    }
    generatingQuiz = { ...generatingQuiz, [course.id]: false };
  }

  function exportQuizText(quiz) {
    let text = `QCM — ${quiz.courseTitle}\n${'='.repeat(50)}\n\n`;
    quiz.questions.forEach((q, i) => {
      text += `${i+1}. ${q.question}\n`;
      q.options.forEach(opt => { text += `   ${opt}\n`; });
      text += `   ✅ Réponse correcte : ${q.correct}\n`;
      text += `   💡 ${q.explanation}\n\n`;
    });
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `QCM_${quiz.courseTitle.replace(/\s+/g, '_')}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  // ── Assignments ────────────────────────────────────────────────────────────
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

  // ── Courses ────────────────────────────────────────────────────────────────
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

  function handleFileSelect(e) { selectedFile = e.target.files[0]; }

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
      const url = modalMode === 'create' ? `${API}/api/v1/courses` : `${API}/api/v1/courses/${editingCourse.id}`;
      const res = await fetch(url, { method: modalMode === 'create' ? 'POST' : 'PUT', headers: t ? { Authorization: `Bearer ${t}` } : {}, body: fd });
      if (!res.ok) throw new Error(await res.text());
      showSuccess(modalMode === 'create' ? 'Cours créé !' : 'Cours modifié !');
      showCourseModal = false;
      courses = await apiFetch('/api/v1/courses');
      await checkAllIndexed();
    } catch(e) { alert('Erreur: ' + e.message); } finally { uploading = false; }
  }

  async function deleteCourse(id) {
    if (!confirm('Supprimer ce cours ?')) return;
    try {
      await apiFetch(`/api/v1/courses/${id}`, { method: 'DELETE' });
      courses = courses.filter(c => c.id !== id);
      showSuccess('Cours supprimé !');
    } catch(e) { alert('Erreur: ' + e.message); }
  }

  function viewCourse(c) { viewingCourse = c; showCourseViewer = true; }

  function downloadCourse(c) {
    const t = getToken();
    const a = document.createElement('a');
    a.href = `${API}/api/v1/courses/${c.id}/file` + (t ? `?token=${t}` : '');
    a.download = c.original_filename || c.filename;
    a.click();
  }

  function getCourseFileUrl(c) {
    const t = getToken();
    return `${API}/api/v1/courses/${c.id}/file${t ? `?token=${t}` : ''}`;
  }

  async function regenerateCode() {
    try { classroom = await apiFetch('/api/v1/classroom/regenerate', { method: 'POST' }); showSuccess('Nouveau code !'); }
    catch(e) { alert('Erreur: ' + e.message); }
  }

  function showSuccess(msg) { successMsg = msg; setTimeout(() => successMsg = '', 4000); }

  function formatSize(bytes) {
    if (!bytes) return '-';
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

  function formatDeadline(d) {
    const days = Math.ceil((new Date(d) - new Date()) / 86400000);
    if (days < 0)   return { label: 'Expiré',           color: '#dc2626', bg: '#fef2f2' };
    if (days === 0) return { label: "Aujourd'hui",       color: '#d97706', bg: '#fffbeb' };
    if (days <= 3)  return { label: `${days}j restants`, color: '#d97706', bg: '#fffbeb' };
    return               { label: `${days}j restants`, color: '#059669', bg: '#f0fdf4' };
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
  :global(body) { margin: 0; padding: 0; }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  .layout {
    display: flex;
    width: 100vw;
    height: 100vh;
    background: #f8fafc !important;
    font-family: 'Segoe UI', system-ui, sans-serif;
    color: #1e293b !important;
    color-scheme: light;
    overflow: hidden;
  }

  /* Sidebar */
  .sidebar {
    width: 240px; background: #ffffff !important;
    border-right: 1px solid #e2e8f0;
    flex-shrink: 0; display: flex; flex-direction: column;
    height: 100vh; overflow-y: auto;
  }

  .sidebar-logo { padding: 20px 24px; border-bottom: 1px solid #e2e8f0; font-size: 1.2rem; font-weight: 800; color: #4f46e5 !important; }
  .sidebar-logo span { color: #0ea5e9 !important; }

  .sidebar-user { padding: 16px 20px; border-bottom: 1px solid #e2e8f0; display: flex; align-items: center; gap: 10px; }

  .user-avatar {
    width: 36px; height: 36px; border-radius: 50%;
    background: linear-gradient(135deg, #4f46e5, #0ea5e9);
    display: flex; align-items: center; justify-content: center;
    color: white !important; font-weight: 700; font-size: 14px; flex-shrink: 0;
  }

  .user-name { font-size: 13px; font-weight: 600; color: #1e293b !important; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .user-role { font-size: 11px; color: #64748b !important; }

  .nav { padding: 12px 0; flex: 1; }

  .nav-item {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 20px; cursor: pointer;
    font-size: 14px; font-weight: 500; color: #64748b !important;
    border-left: 3px solid transparent; transition: all 0.15s;
    background: transparent !important;
  }
  .nav-item:hover { background: #f8fafc !important; color: #4f46e5 !important; }
  .nav-item.active { background: #eef2ff !important; color: #4f46e5 !important; border-left-color: #4f46e5; font-weight: 600; }

  .nav-badge { margin-left: auto; background: #4f46e5 !important; color: white !important; font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: 20px; }

  /* Main */
  .main { flex: 1; min-width: 0; display: flex; flex-direction: column; height: 100vh; overflow: hidden; background: #f8fafc !important; }

  .topbar { background: #ffffff !important; border-bottom: 1px solid #e2e8f0; padding: 16px 28px; display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; z-index: 10; }

  .page-title { font-size: 20px; font-weight: 700; color: #1e293b !important; }
  .page-sub { font-size: 13px; color: #94a3b8 !important; margin-top: 2px; }

  .content { flex: 1; overflow-y: auto; padding: 24px 28px; }

  /* Buttons */
  .btn { padding: 8px 16px; border-radius: 8px; border: 1px solid #e2e8f0; background: #ffffff !important; color: #374151 !important; cursor: pointer; font-size: 13px; font-weight: 500; display: inline-flex; align-items: center; gap: 6px; font-family: inherit; transition: all 0.15s; }
  .btn:hover { background: #f8fafc !important; }
  .btn-primary { background: #4f46e5 !important; color: white !important; border: none; padding: 9px 18px; border-radius: 9px; font-size: 13px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; font-family: inherit; transition: all 0.15s; box-shadow: 0 1px 3px rgba(79,70,229,0.3); }
  .btn-primary:hover { background: #4338ca !important; transform: translateY(-1px); }
  .btn-primary:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
  .btn-danger { color: #dc2626 !important; border-color: #fca5a5; background: #fef2f2 !important; }
  .btn-danger:hover { background: #fee2e2 !important; }
  .btn-success { color: #059669 !important; border-color: #6ee7b7; background: #f0fdf4 !important; }
  .btn-success:hover { background: #dcfce7 !important; }
  .btn-quiz { color: #7c3aed !important; border-color: #c4b5fd; background: #faf5ff !important; }
  .btn-quiz:hover { background: #f3e8ff !important; }
  .btn-quiz:disabled { opacity: 0.6; cursor: wait; }

  /* Stats */
  .stats { display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; margin-bottom: 24px; }
  .stat-card { background: #ffffff !important; border-radius: 14px; padding: 18px 20px; border: 1px solid #e2e8f0; display: flex; align-items: center; gap: 14px; transition: box-shadow 0.15s; }
  .stat-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.07); }
  .stat-icon { width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 20px; }
  .stat-val { font-size: 24px; font-weight: 800; color: #1e293b !important; }
  .stat-lbl { font-size: 12px; color: #94a3b8 !important; font-weight: 500; margin-top: 2px; }

  /* Devoirs */
  .devoir-card { background: #ffffff !important; border-radius: 12px; border: 1px solid #e2e8f0; padding: 14px 18px; display: flex; align-items: center; gap: 14px; margin-bottom: 10px; transition: all 0.15s; }
  .devoir-card:hover { box-shadow: 0 3px 10px rgba(0,0,0,0.07); border-color: #c7d2fe; }
  .devoir-icon { width: 40px; height: 40px; border-radius: 10px; background: #eef2ff !important; display: flex; align-items: center; justify-content: center; font-size: 18px; flex-shrink: 0; }
  .devoir-info { flex: 1; min-width: 0; }
  .devoir-title { font-weight: 600; font-size: 14px; color: #1e293b !important; margin-bottom: 4px; }
  .devoir-meta { font-size: 12px; color: #94a3b8 !important; display: flex; gap: 12px; flex-wrap: wrap; }

  /* Courses */
  .courses-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px,1fr)); gap: 16px; }
  .course-card { background: #ffffff !important; border-radius: 16px; border: 1px solid #e2e8f0; padding: 20px; display: flex; flex-direction: column; gap: 12px; transition: all 0.2s; }
  .course-card:hover { box-shadow: 0 6px 20px rgba(0,0,0,0.08); transform: translateY(-2px); }
  .course-title { font-size: 15px; font-weight: 700; color: #1e293b !important; }
  .course-desc { font-size: 12px; color: #94a3b8 !important; line-height: 1.5; }
  .course-meta { font-size: 12px; color: #cbd5e1 !important; display: flex; gap: 10px; flex-wrap: wrap; }
  .course-actions { display: flex; gap: 8px; }

  /* Badges */
  .badge { display: inline-flex; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; white-space: nowrap; align-items: center; gap: 4px; }
  .badge-module  { background: #eef2ff !important; color: #4f46e5 !important; border: 1px solid #c7d2fe; }
  .badge-active  { background: #f0fdf4 !important; color: #059669 !important; border: 1px solid #6ee7b7; }
  .badge-indexed { background: #f0fdf4 !important; color: #059669 !important; border: 1px solid #6ee7b7; }
  .badge-pending { background: #fffbeb !important; color: #d97706 !important; border: 1px solid #fde68a; }

  /* Filters */
  .filter-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 18px; }
  .filter-btn { padding: 5px 14px; border-radius: 20px; border: 1px solid #e2e8f0; background: #ffffff !important; color: #64748b !important; font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit; transition: all 0.15s; }
  .filter-btn.active { background: #4f46e5 !important; color: white !important; border-color: #4f46e5; }
  .filter-btn:hover:not(.active) { border-color: #a5b4fc; color: #4f46e5 !important; }

  /* Index button */
  .btn-index { width: 100%; padding: 9px; border-radius: 9px; border: 1.5px dashed #c7d2fe; background: #f8f9ff !important; color: #4f46e5 !important; font-size: 12px; font-weight: 600; cursor: pointer; font-family: inherit; transition: all 0.2s; display: flex; align-items: center; justify-content: center; gap: 6px; }
  .btn-index:hover:not(:disabled) { background: #eef2ff !important; border-color: #4f46e5; border-style: solid; }
  .btn-index.indexed { color: #059669 !important; border-color: #6ee7b7; border-style: solid; background: #f0fdf4 !important; cursor: default; }
  .btn-index:disabled:not(.indexed) { color: #d97706 !important; border-color: #fde68a; border-style: solid; background: #fffbeb !important; cursor: wait; }

  /* Table */
  .table-wrap { border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; }
  table { width: 100%; border-collapse: collapse; background: #ffffff !important; }
  th { background: #f8fafc !important; padding: 11px 16px; text-align: left; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: #94a3b8 !important; border-bottom: 1px solid #e2e8f0; }
  td { padding: 12px 16px; border-bottom: 1px solid #f1f5f9; font-size: 13px; color: #374151 !important; background: #ffffff !important; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #f8fafc !important; }

  /* Class code */
  .code-display { background: linear-gradient(135deg, #4f46e5, #0ea5e9); border-radius: 16px; padding: 32px; text-align: center; color: white !important; max-width: 420px; margin: 0 auto; }
  .code-label { font-size: 12px; font-weight: 600; opacity: 0.75; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; color: white !important; }
  .code-value { font-size: 3rem; font-weight: 900; letter-spacing: 0.5rem; margin-bottom: 16px; color: white !important; }
  .code-hint { font-size: 13px; opacity: 0.8; color: white !important; }
  .code-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 20px; }
  .code-stat { background: rgba(255,255,255,0.15); border-radius: 10px; padding: 12px; }
  .code-stat-val { font-size: 20px; font-weight: 800; color: white !important; }
  .code-stat-lbl { font-size: 11px; opacity: 0.75; margin-top: 2px; color: white !important; }

  /* Upload */
  .upload-zone { display: block; border: 2px dashed #c7d2fe; border-radius: 12px; padding: 24px; text-align: center; cursor: pointer; transition: all 0.2s; background: #f8f9ff !important; color: #64748b !important; }
  .upload-zone:hover { border-color: #4f46e5; background: #eef2ff !important; }
  .upload-zone.has-file { border-color: #6ee7b7; background: #f0fdf4 !important; }
  .upload-input { display: none; }

  /* Modal */
  .overlay { position: fixed; inset: 0; background: rgba(15,23,42,0.5); backdrop-filter: blur(4px); z-index: 200; display: flex; align-items: center; justify-content: center; padding: 16px; }
  .modal { background: #ffffff !important; border-radius: 18px; padding: 28px; width: 100%; max-width: 520px; max-height: 90vh; overflow-y: auto; box-shadow: 0 20px 60px rgba(0,0,0,0.15); }
  .modal-lg { max-width: 860px; height: 85vh; display: flex; flex-direction: column; }
  .modal-title { font-size: 18px; font-weight: 700; color: #1e293b !important; margin-bottom: 20px; }
  .fg { margin-bottom: 14px; }
  label { display: block; font-size: 12px; font-weight: 600; color: #64748b !important; margin-bottom: 5px; text-transform: uppercase; letter-spacing: 0.4px; }
  input, textarea, select { width: 100%; background: #f8fafc !important; border: 1px solid #e2e8f0; border-radius: 9px; padding: 9px 12px; color: #1e293b !important; font-size: 14px; outline: none; transition: border-color 0.15s; font-family: inherit; }
  input:focus, textarea:focus, select:focus { border-color: #4f46e5; background: white !important; }
  textarea { resize: vertical; min-height: 80px; }
  .frow { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .mactions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px; }

  /* Viewer */
  .viewer-body { flex: 1; min-height: 0; }
  .pdf-frame { width: 100%; height: 100%; border: none; border-radius: 10px; }
  .viewer-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
  .viewer-title { font-size: 16px; font-weight: 700; color: #1e293b !important; }

  /* Quiz */
  .quiz-question {
    margin-bottom: 20px; background: #f8fafc !important;
    border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px;
  }
  .quiz-q-text { font-weight: 600; color: #1e293b !important; margin-bottom: 10px; font-size: 14px; }
  .quiz-option {
    padding: 7px 12px; border-radius: 8px; font-size: 13px;
    margin-bottom: 5px; color: #374151 !important;
    background: #ffffff !important;
  }
  .quiz-option.correct { background: #f0fdf4 !important; color: #059669 !important; font-weight: 600; border: 1px solid #6ee7b7; }
  .quiz-explanation { font-size: 12px; color: #64748b !important; margin-top: 8px; font-style: italic; padding: 6px 10px; background: #fffbeb !important; border-radius: 6px; border-left: 3px solid #f59e0b; }

  /* Toast */
  .toast { position: fixed; bottom: 20px; right: 20px; z-index: 300; background: #1e293b !important; color: white !important; padding: 12px 18px; border-radius: 10px; font-size: 13px; font-weight: 500; box-shadow: 0 8px 24px rgba(0,0,0,0.15); animation: slideIn 0.3s ease; }
  @keyframes slideIn { from { opacity:0; transform: translateY(10px); } to { opacity:1; transform: translateY(0); } }

  /* Misc */
  .empty { text-align: center; padding: 48px 0; color: #94a3b8 !important; }
  .spin { display: flex; align-items: center; justify-content: center; height: 200px; color: #94a3b8 !important; gap: 10px; }
  .spinner { width: 20px; height: 20px; border: 2px solid #e2e8f0; border-top-color: #4f46e5; border-radius: 50%; animation: spin 0.7s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  @media (max-width: 640px) {
    .sidebar { display: none; }
    .stats { grid-template-columns: repeat(2,1fr); }
    .courses-grid { grid-template-columns: 1fr; }
  }
</style>

<div class="layout">

  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="sidebar-logo">Open<span>TutorAI</span></div>
    {#if $user}
      <div class="sidebar-user">
        <div class="user-avatar">{($user.name||'P')[0].toUpperCase()}</div>
        <div>
          <div class="user-name">{$user.name}</div>
          <div class="user-role">Enseignant</div>
        </div>
      </div>
    {/if}
    <nav class="nav">
      {#each [
        { id:'assignments', icon:'📋', label:'Devoirs',   count: assignments.length },
        { id:'courses',     icon:'📚', label:'Cours',     count: courses.length },
        { id:'students',    icon:'👥', label:'Étudiants', count: students.length },
        { id:'classroom',   icon:'🏫', label:'Ma Classe', count: null },
      ] as tab}
        <div class="nav-item {activeTab===tab.id?'active':''}" on:click={() => activeTab=tab.id} role="button" tabindex="0">
          <span>{tab.icon}</span><span>{tab.label}</span>
          {#if tab.count !== null && tab.count > 0}<span class="nav-badge">{tab.count}</span>{/if}
        </div>
      {/each}
    </nav>
  </aside>

  <!-- Main -->
  <div class="main">
    <div class="topbar">
      <div>
        <div class="page-title">
          {activeTab==='assignments'?'📋 Devoirs':activeTab==='courses'?'📚 Cours':activeTab==='students'?'👥 Étudiants':'🏫 Ma Classe'}
        </div>
        <div class="page-sub">
          {activeTab==='assignments'?`${assignments.length} devoir(s)`:activeTab==='courses'?`${courses.length} cours`:activeTab==='students'?`${students.length} étudiant(s)`:classroom?`Code : ${classroom.class_code}`:''}
        </div>
      </div>
      <div>
        {#if activeTab==='assignments'}<button class="btn-primary" on:click={openCreate}>+ Nouveau devoir</button>
        {:else if activeTab==='courses'}<button class="btn-primary" on:click={openCreateCourse}>+ Nouveau cours</button>
        {:else if activeTab==='classroom'}<button class="btn" on:click={regenerateCode}>🔄 Nouveau code</button>
        {/if}
      </div>
    </div>

    <div class="content">
      {#if loading}
        <div class="spin"><div class="spinner"></div> Chargement...</div>

      {:else if activeTab==='assignments'}
        <div class="stats">
          {#each [
            {icon:'📋',bg:'#eef2ff',val:assignments.length,lbl:'Total'},
            {icon:'✅',bg:'#f0fdf4',val:assignments.filter(a=>a.status==='active').length,lbl:'Actifs'},
            {icon:'📨',bg:'#fff7ed',val:assignments.reduce((s,a)=>s+(a.submission_count||0),0),lbl:'Soumissions'},
            {icon:'👥',bg:'#f0f9ff',val:students.length,lbl:'Étudiants'},
          ] as s}
            <div class="stat-card">
              <div class="stat-icon" style="background:{s.bg}">{s.icon}</div>
              <div><div class="stat-val">{s.val}</div><div class="stat-lbl">{s.lbl}</div></div>
            </div>
          {/each}
        </div>
        {#if assignments.length===0}
          <div class="empty"><div style="font-size:48px">📋</div><p style="margin-top:12px">Aucun devoir. Créez votre premier devoir !</p></div>
        {:else}
          {#each assignments as a}
            {@const d=formatDeadline(a.due_date)}
            <div class="devoir-card">
              <div class="devoir-icon">📋</div>
              <div class="devoir-info">
                <div class="devoir-title">{a.title}</div>
                <div class="devoir-meta">
                  {#if a.course}<span>📚 {a.course}</span>{/if}
                  <span>📅 {a.due_date} à {a.due_time}</span>
                  <span>⭐ {a.points} pts</span>
                  <span>📨 {a.submission_count||0} soumissions</span>
                </div>
              </div>
              <span class="badge" style="background:{d.bg};color:{d.color}">{d.label}</span>
              <span class="badge {a.status==='active'?'badge-active':''}">{a.status==='active'?'Actif':'Fermé'}</span>
              <div style="display:flex;gap:6px">
                <button class="btn" on:click={() => openEdit(a)}>✏️</button>
                <button class="btn btn-danger" on:click={() => deleteAssignment(a.id)}>🗑️</button>
              </div>
            </div>
          {/each}
        {/if}

      {:else if activeTab==='courses'}
        {#if courses.length>0}
          <div class="filter-bar">
            <button class="filter-btn {filterModule==='all'?'active':''}" on:click={()=>filterModule='all'}>Tous ({courses.length})</button>
            {#each uniqueModules as m}
              <button class="filter-btn {filterModule===m?'active':''}" on:click={()=>filterModule=m}>{m}</button>
            {/each}
          </div>
        {/if}
        {#if filteredCourses.length===0}
          <div class="empty"><div style="font-size:48px">📚</div><p style="margin-top:12px">Aucun cours. Créez votre premier cours !</p></div>
        {:else}
          <div class="courses-grid">
            {#each filteredCourses as c}
              <div class="course-card">
                <div style="display:flex;align-items:flex-start;justify-content:space-between">
                  <span style="font-size:2.2rem">{fileIcon(c.file_type)}</span>
                  <div style="display:flex;flex-direction:column;align-items:flex-end;gap:5px">
                    <span class="badge badge-module">{c.module}</span>
                    {#if indexedCourses[c.id]}
                      <span class="badge badge-indexed">🤖 Indexé</span>
                    {:else}
                      <span class="badge badge-pending">⚠️ Non indexé</span>
                    {/if}
                  </div>
                </div>
                <div class="course-title">{c.title}</div>
                {#if c.description}<div class="course-desc">{c.description}</div>{/if}
                <div class="course-meta">
                  <span>📦 {formatSize(c.file_size)}</span>
                  <span>👤 {c.teacher_name||'Enseignant'}</span>
                  <span>{c.file_type?.replace('.','').toUpperCase()}</span>
                </div>
                <div class="course-actions">
                  <button class="btn btn-success" style="flex:1" on:click={()=>viewCourse(c)}>👁️ Lire</button>
                  <button class="btn" on:click={()=>downloadCourse(c)}>⬇️</button>
                  <button class="btn" on:click={()=>openEditCourse(c)}>✏️</button>
                  <button class="btn btn-danger" on:click={()=>deleteCourse(c.id)}>🗑️</button>
                </div>

                <!-- Bouton Indexer -->
                <button
                  class="btn-index {indexedCourses[c.id]?'indexed':''}"
                  on:click={()=>indexCourse(c.id)}
                  disabled={indexingCourseId===c.id||indexedCourses[c.id]}
                >
                  {#if indexingCourseId===c.id}
                    <div class="spinner" style="width:12px;height:12px;border-width:2px"></div> Indexation en cours...
                  {:else if indexedCourses[c.id]}
                    🤖 Cours indexé pour le chatbot IA
                  {:else}
                    🤖 Indexer pour le chatbot IA
                  {/if}
                </button>

                <!-- Bouton Générer QCM -->
                {#if indexedCourses[c.id]}
                  <button
                    class="btn btn-quiz"
                    style="width:100%;justify-content:center"
                    on:click={()=>generateQuiz(c)}
                    disabled={generatingQuiz[c.id]}
                  >
                    {#if generatingQuiz[c.id]}
                      <div class="spinner" style="width:12px;height:12px;border-width:2px;border-top-color:#7c3aed"></div> Génération QCM...
                    {:else}
                      📝 Générer un QCM
                    {/if}
                  </button>
                {/if}
              </div>
            {/each}
          </div>
        {/if}

      {:else if activeTab==='students'}
        {#if students.length===0}
          <div class="empty"><div style="font-size:48px">👥</div><p style="margin-top:12px">Aucun étudiant inscrit.</p></div>
        {:else}
          <div class="table-wrap">
            <table>
              <thead><tr><th>Nom</th><th>Email</th><th>Rôle</th></tr></thead>
              <tbody>
                {#each students as s}
                  <tr>
                    <td>
                      <div style="display:flex;align-items:center;gap:10px">
                        <div style="width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,#4f46e5,#0ea5e9);display:flex;align-items:center;justify-content:center;color:white;font-weight:700;font-size:12px;flex-shrink:0">
                          {(s.name||'?')[0].toUpperCase()}
                        </div>
                        {s.name}
                      </div>
                    </td>
                    <td>{s.email}</td>
                    <td><span class="badge badge-active">{s.role}</span></td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}

      {:else if activeTab==='classroom'}
        {#if classroom}
          <div class="code-display">
            <div class="code-label">Code de classe</div>
            <div class="code-value">{classroom.class_code}</div>
            <div class="code-hint">Partagez ce code avec vos étudiants.</div>
            <div class="code-stats">
              <div class="code-stat"><div class="code-stat-val">{classroom.student_count||0}</div><div class="code-stat-lbl">Étudiants</div></div>
              <div class="code-stat"><div class="code-stat-val">{assignments.length}</div><div class="code-stat-lbl">Devoirs</div></div>
            </div>
          </div>
        {:else}
          <div class="empty">🏫 Impossible de charger la classe.</div>
        {/if}
      {/if}
    </div>
  </div>
</div>

<!-- Modal Devoirs -->
{#if showModal}
  <div class="overlay" on:click|self={()=>showModal=false}>
    <div class="modal">
      <div class="modal-title">{modalMode==='create'?'➕ Nouveau devoir':'✏️ Modifier le devoir'}</div>
      <div class="fg"><label>Titre *</label><input bind:value={form.title} placeholder="Titre du devoir"/></div>
      <div class="fg"><label>Description</label><textarea bind:value={form.description} placeholder="Instructions..."></textarea></div>
      <div class="fg"><label>Cours / Matière</label><input bind:value={form.course} placeholder="Ex: Mathématiques"/></div>
      <div class="frow">
        <div class="fg"><label>Date limite *</label><input type="date" bind:value={form.due_date}/></div>
        <div class="fg"><label>Heure limite</label><input type="time" bind:value={form.due_time}/></div>
      </div>
      <div class="fg"><label>Points</label><input type="number" bind:value={form.points} min="0"/></div>
      <div class="mactions">
        <button class="btn" on:click={()=>showModal=false}>Annuler</button>
        <button class="btn-primary" on:click={submitForm}>{modalMode==='create'?'Créer':'Enregistrer'}</button>
      </div>
    </div>
  </div>
{/if}

<!-- Modal Cours -->
{#if showCourseModal}
  <div class="overlay" on:click|self={()=>showCourseModal=false}>
    <div class="modal">
      <div class="modal-title">{modalMode==='create'?'📚 Nouveau cours':'✏️ Modifier le cours'}</div>
      <div class="fg"><label>Titre *</label><input bind:value={courseForm.title} placeholder="Titre du cours"/></div>
      <div class="fg"><label>Description</label><textarea bind:value={courseForm.description} placeholder="Objectifs..."></textarea></div>
      <div class="fg">
        <label>Module *</label>
        <select bind:value={courseForm.module}>{#each MODULES as m}<option value={m}>{m}</option>{/each}</select>
      </div>
      <div class="fg">
        <label>Fichier {modalMode==='create'?'*':'(optionnel)'}</label>
        <label class="upload-zone {selectedFile?'has-file':''}" for="file-input">
          {#if selectedFile}
            <div>✅ {selectedFile.name}</div>
            <div style="font-size:12px;color:#94a3b8;margin-top:4px">{formatSize(selectedFile.size)}</div>
          {:else}
            <div>📎 Cliquez pour sélectionner un fichier</div>
            <div style="font-size:12px;color:#94a3b8;margin-top:4px">PDF, Word, PowerPoint, TXT</div>
          {/if}
        </label>
        <input id="file-input" class="upload-input" type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.txt" on:change={handleFileSelect}/>
      </div>
      <div class="mactions">
        <button class="btn" on:click={()=>showCourseModal=false}>Annuler</button>
        <button class="btn-primary" on:click={submitCourseForm} disabled={uploading}>
          {uploading?'⏳ Envoi...':modalMode==='create'?'Créer le cours':'Enregistrer'}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- Modal PDF Viewer -->
{#if showCourseViewer && viewingCourse}
  <div class="overlay" on:click|self={()=>showCourseViewer=false}>
    <div class="modal modal-lg">
      <div class="viewer-header">
        <div>
          <div class="viewer-title">{fileIcon(viewingCourse.file_type)} {viewingCourse.title}</div>
          <div style="font-size:12px;color:#94a3b8">{viewingCourse.module}</div>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn" on:click={()=>downloadCourse(viewingCourse)}>⬇️ Télécharger</button>
          <button class="btn btn-danger" on:click={()=>showCourseViewer=false}>✕ Fermer</button>
        </div>
      </div>
      <div class="viewer-body">
        {#if viewingCourse.file_type==='.pdf'}
          <iframe class="pdf-frame" src="{getCourseFileUrl(viewingCourse)}" title={viewingCourse.title}></iframe>
        {:else}
          <div class="empty" style="height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center">
            <div style="font-size:3rem">{fileIcon(viewingCourse.file_type)}</div>
            <p style="margin-top:12px;color:#94a3b8">Aperçu non disponible.</p>
            <button class="btn-primary" style="margin-top:12px" on:click={()=>downloadCourse(viewingCourse)}>⬇️ Télécharger</button>
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}

<!-- Modal QCM -->
{#if showQuizModal && currentQuiz}
  <div class="overlay" on:click|self={()=>showQuizModal=false}>
    <div class="modal" style="max-width:700px;max-height:90vh;overflow-y:auto">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
        <div>
          <div class="modal-title" style="margin:0">📝 QCM — {currentQuiz.courseTitle}</div>
          <div style="font-size:13px;color:#94a3b8;margin-top:4px">{currentQuiz.questions?.length||0} questions générées par IA</div>
        </div>
        <button class="btn btn-danger" on:click={()=>showQuizModal=false}>✕</button>
      </div>

      {#if currentQuiz.questions && currentQuiz.questions.length > 0}
        {#each currentQuiz.questions as q, i}
          <div class="quiz-question">
            <div class="quiz-q-text">{i+1}. {q.question}</div>
            {#each q.options as opt}
              <div class="quiz-option {opt.startsWith(q.correct)?'correct':''}">
                {opt} {opt.startsWith(q.correct)?'✅':''}
              </div>
            {/each}
            <div class="quiz-explanation">💡 {q.explanation}</div>
          </div>
        {/each}

        <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:20px">
          <button class="btn" on:click={()=>showQuizModal=false}>Fermer</button>
          <button class="btn-primary" on:click={()=>exportQuizText(currentQuiz)}>⬇️ Exporter en .txt</button>
        </div>
      {:else}
        <div class="empty">
          <div style="font-size:48px">❓</div>
          <p style="margin-top:12px">Aucune question générée. Essayez avec un cours plus détaillé.</p>
        </div>
      {/if}
    </div>
  </div>
{/if}

{#if successMsg}<div class="toast">{successMsg}</div>{/if}