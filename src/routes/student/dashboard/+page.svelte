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

  // ── Quiz State ──
  let quizzes: any[] = [];
  let selectedQuiz: any = null;
  let currentAnswers: any = {};
  let showQuizResults: any = null;
  let quizLoading = false;

  // Réactivité: recalculer les stats quand quizzes change
  $: passedCount = quizzes.filter(q => q.already_submitted).length;
  $: todoCount = quizzes.filter(q => !q.already_submitted).length;

  // Rejoindre une classe
  let showJoinModal = false;
  let joinCode = '';
  let joinLoading = false;
  let joinError = '';
  let joinSuccess = '';

  const API = 'http://localhost:8080';

  // ── Auth ──────────────────────────────────────────────────
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
        ...(options.headers || {}),
      },
    });
    if (!res.ok) throw new Error(`${res.status}`);
    return res.json();
  }

  // ── Chargement des données ────────────────────────────────
  async function loadAll() {
    loading = true;
    try {
      classrooms = await apiFetch('/api/v1/my-classrooms');
    } catch {
      classrooms = [];
    }

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
    await loadQuizzes();
    loading = false;
  }

  // ── Quiz ──────────────────────────────────────────────────
  async function loadQuizzes() {
    try {
      const t = getToken();
      const res = await fetch(`${API}/api/v1/quizzes`, {
        headers: t ? { Authorization: `Bearer ${t}` } : {}
      });
      if (!res.ok) { quizzes = []; return; }

      let data = await res.json();
      data = data.filter((q: any) => q.status === 'published');

      // Vérifier les soumissions pour chaque quiz
      for (const quiz of data) {
        try {
          const subRes = await fetch(`${API}/api/v1/quizzes/${quiz.id}/submission`, {
            headers: t ? { Authorization: `Bearer ${t}` } : {}
          });
          if (subRes.ok) {
            const subData = await subRes.json();
            if (subData && (subData.score !== undefined || subData.answers)) {
              quiz.already_submitted = true;
              quiz.submission = {
                score: subData.score,
                total: subData.total || quiz.question_count || 1,
                score_pct: subData.score_pct || Math.round((subData.score / (subData.total || quiz.question_count || 1)) * 100),
                ai_note: subData.ai_note,
                ai_feedback: subData.ai_feedback
              };
            }
          }
        } catch(e) { /* pas de soumission */ }
      }

      quizzes = data;
    } catch(e) { quizzes = []; }
  }

  async function startQuiz(quiz: any) {
    quizLoading = true;
    try {
      const t = getToken();
      const res = await fetch(`${API}/api/v1/quizzes/${quiz.id}`, {
        headers: t ? { Authorization: `Bearer ${t}` } : {}
      });
      if (!res.ok) { alert('Erreur chargement quiz'); quizLoading = false; return; }
      const data = await res.json();
      selectedQuiz = {
        ...data,
        questions: (data.questions || []).map((q: any, i: number) => ({
          id: q.id || String(i),
          question: q.question_text || q.question || '',
          options: {
            A: q.option_a || (q.options && q.options[0]) || '',
            B: q.option_b || (q.options && q.options[1]) || '',
            C: q.option_c || (q.options && q.options[2]) || '',
            D: q.option_d || (q.options && q.options[3]) || '',
          }
        }))
      };
      currentAnswers = {};
      showQuizResults = null;
      setTimeout(() => {
        const main = document.querySelector('.main');
        if (main) main.scrollTo({ top: 0, behavior: 'smooth' });
      }, 50);
    } catch(e) { alert('Erreur: ' + e); }
    quizLoading = false;
  }

  async function submitQuiz() {
    const quizId = selectedQuiz.id;
    try {
      const t = getToken();
      const formattedAnswers: any = {};
      selectedQuiz.questions.forEach((q: any, i: number) => {
        if (currentAnswers[q.id] !== undefined) {
          formattedAnswers[String(i)] = currentAnswers[q.id];
        }
      });
      const res = await fetch(`${API}/api/v1/quizzes/${quizId}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(t ? { Authorization: `Bearer ${t}` } : {}) },
        body: JSON.stringify({ answers: formattedAnswers })
      });
      if (res.ok) {
        const resultData = await res.json();
        showQuizResults = resultData;
        selectedQuiz = null;

        // Mettre à jour immédiatement le quiz dans la liste locale
        const idx = quizzes.findIndex(q => q.id === quizId);
        if (idx !== -1) {
          quizzes[idx] = {
            ...quizzes[idx],
            already_submitted: true,
            submission: {
              score: resultData.score,
              total: resultData.total,
              score_pct: resultData.score_pct,
              ai_note: resultData.ai_note,
              ai_feedback: resultData.ai_feedback
            }
          };
          // FORCER la réactivité Svelte avec une nouvelle référence
          quizzes = [...quizzes];
        }

        // Recharger depuis le serveur en arrière-plan
        await loadQuizzes();
        setTimeout(() => {
          const main = document.querySelector('.main');
          if (main) main.scrollTo({ top: 0, behavior: 'smooth' });
        }, 50);
      } else {
        const err = await res.json().catch(() => ({}));
        alert(err.detail || 'Erreur soumission');
      }
    } catch(e) { alert('Erreur: ' + e); }
  }

  function selectAnswer(questionId: string, answer: string) {
    currentAnswers = { ...currentAnswers, [questionId]: answer };
  }

  // ── Rejoindre une classe ──────────────────────────────────
  async function joinClassroom() {
    if (!joinCode.trim()) { joinError = 'Veuillez entrer un code.'; return; }
    joinLoading = true;
    joinError = '';
    joinSuccess = '';
    try {
      await apiFetch('/api/v1/join-classroom', {
        method: 'POST',
        body: JSON.stringify({ code: joinCode.trim().toUpperCase() }),
      });
      joinSuccess = 'Vous avez rejoint la classe avec succès !';
      joinCode = '';
      joinCode = '';
      await loadAll();
      setTimeout(() => { showJoinModal = false; joinSuccess = ''; }, 2000);
    } catch (e: any) {
      joinError = 'Code invalide ou classe introuvable.';
    }
    joinLoading = false;
  }

  // ── Utilitaires ───────────────────────────────────────────
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

  function fileIcon(type: string): string {
    if (type === '.pdf') return '📄';
    if (['.doc', '.docx'].includes(type)) return '📝';
    if (['.ppt', '.pptx'].includes(type)) return '📊';
    return '📁';
  }

  function formatSize(bytes: number): string {
    if (!bytes) return '—';
    if (bytes < 1024) return bytes + ' o';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' Ko';
    return (bytes / (1024 * 1024)).toFixed(1) + ' Mo';
  }

  // ── Viewer PDF ────────────────────────────────────────────
  function openPdf(url: string, title: string) {
    selectedPdf = { url, title };
  }
  function closePdf() { selectedPdf = null; }

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
      a.href = URL.createObjectURL(blob);
      a.download = filename || 'document';
      a.click();
      URL.revokeObjectURL(a.href);
    } catch {
      window.open(url, '_blank');
    }
  }

  // ── Lifecycle ─────────────────────────────────────────────
  onMount(async () => {
    if (!$user) { goto('/auth'); return; }
    if ($user.role !== 'user') { goto(`/${$user.role}`); return; }
    await loadAll();
  });
</script>

<style>
.logo-img {
  height: 32px;        /* ajuste selon ta taille */
  width: auto;
  display: block;
}
/* Ajoute ces styles dans ton <style> ou fichier CSS */
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-badge {
  display: flex;
  font-family: 'Segoe UI', system-ui, sans-serif;
  font-weight: 800;
  font-size: 16px;
}

.logo-o {
  background: #2563eb;
  color: white;
  padding: 4px 5px 4px 7px;
  border-radius: 6px 0 0 6px;
  font-size: 15px;
  letter-spacing: -1px;
}

.logo-t {
  background: #1e40af;
  color: white;
  padding: 4px 7px 4px 5px;
  border-radius: 0 6px 6px 0;
  font-size: 15px;
  letter-spacing: -1px;
}

.logo-text {
  font-size: 1.15rem;
  font-weight: 400;
  color: #0f172a;
  letter-spacing: -0.3px;
}

.logo-text strong {
  font-weight: 700;
}
  :global(body) {
    margin: 0;
    padding: 0;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f8fafc;
    color: #1e293b;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  * { box-sizing: border-box; }

  .dash {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    background: #f8fafc;
  }

  /* ════════════════════════════════════════
     HEADER
  ════════════════════════════════════════ */
  .header {
    height: 64px;
    background: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    padding: 0 2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 50;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }

  .logo {
    font-size: 1.35rem;
    font-weight: 800;
    color: #2563eb;
    letter-spacing: -0.5px;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .logo-icon {
    width: 32px;
    height: 32px;
    background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 1rem;
  }

  .user-badge {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.4rem 1rem;
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 500;
    color: #475569;
  }

  .user-avatar {
    width: 28px;
    height: 28px;
    background: linear-gradient(135deg, #2563eb, #3b82f6);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 0.75rem;
    font-weight: 700;
  }

  /* ════════════════════════════════════════
     LAYOUT
  ════════════════════════════════════════ */
  .layout {
    display: flex;
    flex: 1;
    min-height: calc(100vh - 64px);
  }

  /* ════════════════════════════════════════
     SIDEBAR
  ════════════════════════════════════════ */
  .sidebar {
    width: 260px;
    background: #ffffff;
    border-right: 1px solid #e2e8f0;
    padding: 1.5rem 0;
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
  }

  .sidebar-section {
    padding: 0 1rem;
    margin-bottom: 0.5rem;
  }

  .sidebar-label {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #94a3b8;
    padding: 0 0.75rem;
    margin-bottom: 0.5rem;
  }

  .nav-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.65rem 0.875rem;
    margin: 0.15rem 0.75rem;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 500;
    color: #64748b;
    transition: all 0.2s ease;
    border: none;
    background: none;
    width: calc(100% - 1.5rem);
  }

  .nav-item:hover {
    background: #f1f5f9;
    color: #334155;
  }

  .nav-item.active {
    background: #eff6ff;
    color: #2563eb;
    font-weight: 600;
  }

  .nav-icon {
    font-size: 1.1rem;
    width: 24px;
    text-align: center;
    flex-shrink: 0;
  }

  .nav-divider {
    margin: 1rem 1.25rem;
    border: none;
    border-top: 1px solid #e2e8f0;
  }

  .btn-join-sidebar {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.65rem 0.875rem;
    margin: 0.15rem 0.75rem;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 600;
    color: #059669;
    transition: all 0.2s ease;
    border: 1.5px dashed #cbd5e1;
    background: #f8fafc;
    width: calc(100% - 1.5rem);
  }

  .btn-join-sidebar:hover {
    background: #ecfdf5;
    border-color: #059669;
    color: #047857;
  }

  /* ════════════════════════════════════════
     MAIN
  ════════════════════════════════════════ */
  .main {
    flex: 1;
    padding: 2rem;
    overflow-y: auto;
    height: calc(100vh - 64px);
    scroll-behavior: smooth;
  }

  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 2rem;
    flex-wrap: wrap;
    gap: 1rem;
  }

  .page-title-group {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .page-title {
    font-size: 1.75rem;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.025em;
  }

  .page-sub {
    font-size: 0.875rem;
    color: #64748b;
    font-weight: 400;
  }

  .btn {
    padding: 0.55rem 1.1rem;
    border-radius: 10px;
    border: none;
    cursor: pointer;
    font-weight: 600;
    font-size: 0.85rem;
    transition: all 0.2s ease;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-family: inherit;
    white-space: nowrap;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
  }

  .btn-primary {
    background: #2563eb;
    color: #ffffff;
  }
  .btn-primary:hover {
    background: #1d4ed8;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25);
  }

  .btn-secondary {
    background: #ffffff;
    color: #475569;
    border: 1px solid #e2e8f0;
  }
  .btn-secondary:hover {
    background: #f8fafc;
    border-color: #cbd5e1;
  }

  .btn-success {
    background: #059669;
    color: #ffffff;
  }
  .btn-success:hover {
    background: #047857;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(5, 150, 105, 0.25);
  }

  .btn-outline {
    background: transparent;
    color: #475569;
    border: 1px solid #e2e8f0;
  }
  .btn-outline:hover {
    background: #f8fafc;
    border-color: #cbd5e1;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none !important;
    box-shadow: none !important;
  }

  /* ════════════════════════════════════════
     WELCOME BANNER
  ════════════════════════════════════════ */
  .welcome-banner {
    background: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%);
    border: 1px solid #dbeafe;
    border-radius: 16px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 2rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }

  .welcome-icon {
    width: 44px;
    height: 44px;
    background: #dbeafe;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.25rem;
    flex-shrink: 0;
  }

  .welcome-text {
    font-size: 0.95rem;
    color: #475569;
    line-height: 1.5;
  }

  .welcome-text strong {
    color: #1e293b;
    font-weight: 700;
  }

  /* ════════════════════════════════════════
     STATS
  ════════════════════════════════════════ */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
  }

  .stat-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    transition: all 0.2s ease;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }

  .stat-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(0,0,0,0.08);
    border-color: #cbd5e1;
  }

  .stat-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .stat-icon {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1rem;
  }

  .stat-icon.blue { background: #eff6ff; }
  .stat-icon.green { background: #ecfdf5; }
  .stat-icon.orange { background: #fff7ed; }
  .stat-icon.red { background: #fef2f2; }
  .stat-icon.purple { background: #f5f3ff; }

  .stat-num {
    font-size: 1.75rem;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.02em;
  }

  .stat-label {
    font-size: 0.8rem;
    color: #94a3b8;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .stat-trend {
    font-size: 0.75rem;
    color: #059669;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 0.2rem;
  }

  /* ════════════════════════════════════════
     CARDS
  ════════════════════════════════════════ */
  .card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 1.25rem;
    transition: all 0.2s ease;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }

  .card:hover {
    box-shadow: 0 8px 25px rgba(0,0,0,0.06);
    border-color: #cbd5e1;
  }

  .card-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1rem;
  }

  /* Assignment Card */
  .acard {
    display: flex;
    align-items: flex-start;
    gap: 1rem;
    padding: 1.25rem;
    flex-wrap: wrap;
  }

  .acard-icon {
    width: 44px;
    height: 44px;
    background: #eff6ff;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.25rem;
    flex-shrink: 0;
  }

  .acard-info {
    flex: 1;
    min-width: 0;
  }

  .acard-title {
    font-weight: 700;
    font-size: 1rem;
    color: #0f172a;
    margin-bottom: 0.35rem;
  }

  .acard-desc {
    font-size: 0.85rem;
    color: #64748b;
    margin-bottom: 0.5rem;
    line-height: 1.5;
  }

  .acard-meta {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    font-size: 0.8rem;
    color: #94a3b8;
    font-weight: 500;
  }

  .acard-meta span {
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }

  .acard-actions {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-shrink: 0;
  }

  /* Course Card */
  .ccard {
    display: flex;
    flex-direction: column;
    gap: 0.875rem;
    padding: 1.25rem;
    height: 100%;
  }

  .ccard-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .ccard-icon {
    width: 48px;
    height: 48px;
    background: #f1f5f9;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.5rem;
  }

  .ccard-title {
    font-weight: 700;
    font-size: 1rem;
    color: #0f172a;
    line-height: 1.4;
  }

  .ccard-desc {
    font-size: 0.85rem;
    color: #64748b;
    line-height: 1.5;
    flex: 1;
  }

  .ccard-meta {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
    font-size: 0.78rem;
    color: #94a3b8;
    font-weight: 500;
  }

  .ccard-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: auto;
    padding-top: 0.5rem;
    border-top: 1px solid #f1f5f9;
  }

  .ccard-actions .btn {
    flex: 1;
    justify-content: center;
  }

  /* Quiz Card */
  .qcard {
    display: flex;
    flex-direction: column;
    gap: 0.875rem;
    padding: 1.25rem;
    height: 100%;
  }

  .qcard-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .qcard-icon {
    width: 48px;
    height: 48px;
    background: #f5f3ff;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.5rem;
  }

  .qcard-title {
    font-weight: 700;
    font-size: 1rem;
    color: #0f172a;
    line-height: 1.4;
  }

  .qcard-meta {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
    font-size: 0.78rem;
    color: #94a3b8;
    font-weight: 500;
  }

  .qcard-result {
    padding: 0.875rem;
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 10px;
    margin-top: 0.25rem;
  }

  .qcard-result-score {
    font-size: 0.875rem;
    color: #15803d;
    font-weight: 700;
  }

  .qcard-result-note {
    font-size: 0.8rem;
    color: #15803d;
    font-weight: 600;
    margin-top: 0.25rem;
  }

  .qcard-result-feedback {
    font-size: 0.78rem;
    color: #64748b;
    margin-top: 0.5rem;
    line-height: 1.5;
  }

  .qcard-actions {
    margin-top: auto;
    padding-top: 0.5rem;
  }

  .qcard-actions .btn {
    width: 100%;
    justify-content: center;
  }

  /* Badges */
  .badge {
    display: inline-flex;
    align-items: center;
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    white-space: nowrap;
  }

  .badge-blue {
    background: #eff6ff;
    color: #2563eb;
  }

  .badge-green {
    background: #ecfdf5;
    color: #059669;
  }

  .badge-orange {
    background: #fff7ed;
    color: #ea580c;
  }

  .badge-red {
    background: #fef2f2;
    color: #dc2626;
  }

  .badge-gray {
    background: #f1f5f9;
    color: #64748b;
  }

  .badge-purple {
    background: #f5f3ff;
    color: #7c3aed;
  }

  /* ════════════════════════════════════════
     EMPTY STATE
  ════════════════════════════════════════ */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 4rem 2rem;
    text-align: center;
    background: #ffffff;
    border: 1px dashed #e2e8f0;
    border-radius: 16px;
    gap: 1rem;
  }

  .empty-icon {
    width: 64px;
    height: 64px;
    background: #f1f5f9;
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 2rem;
  }

  .empty-title {
    font-size: 1.1rem;
    font-weight: 700;
    color: #334155;
  }

  .empty-desc {
    font-size: 0.875rem;
    color: #94a3b8;
    max-width: 320px;
    line-height: 1.6;
  }

  /* ════════════════════════════════════════
     SPINNER
  ════════════════════════════════════════ */
  .spinner-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 300px;
    gap: 1rem;
  }

  .spinner {
    width: 40px;
    height: 40px;
    border: 3px solid #e2e8f0;
    border-top-color: #2563eb;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .spinner-text {
    font-size: 0.9rem;
    color: #94a3b8;
    font-weight: 500;
  }

  /* ════════════════════════════════════════
     MODAL - Rejoindre
  ════════════════════════════════════════ */
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.6);
    backdrop-filter: blur(4px);
    z-index: 999;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
  }

  .modal {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 20px;
    padding: 2rem;
    width: 100%;
    max-width: 420px;
    box-shadow: 0 25px 50px -12px rgba(0,0,0,0.15);
    animation: modalIn 0.3s ease;
  }

  @keyframes modalIn {
    from { opacity: 0; transform: scale(0.95) translateY(10px); }
    to { opacity: 1; transform: scale(1) translateY(0); }
  }

  .modal-icon {
    width: 56px;
    height: 56px;
    background: #eff6ff;
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.5rem;
    margin-bottom: 1rem;
  }

  .modal-title {
    font-size: 1.25rem;
    font-weight: 800;
    color: #0f172a;
    margin-bottom: 0.35rem;
  }

  .modal-sub {
    font-size: 0.875rem;
    color: #64748b;
    margin-bottom: 1.5rem;
    line-height: 1.5;
  }

  .code-input {
    width: 100%;
    background: #f8fafc;
    border: 2px solid #e2e8f0;
    border-radius: 12px;
    padding: 1rem;
    font-size: 1.5rem;
    font-weight: 800;
    color: #0f172a;
    text-align: center;
    letter-spacing: 0.3rem;
    text-transform: uppercase;
    outline: none;
    transition: all 0.2s ease;
    font-family: inherit;
  }

  .code-input:focus {
    border-color: #2563eb;
    background: #ffffff;
    box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.1);
  }

  .code-input::placeholder {
    color: #cbd5e1;
    font-weight: 600;
  }

  .modal-actions {
    display: flex;
    gap: 0.75rem;
    margin-top: 1.5rem;
  }

  .modal-actions .btn {
    flex: 1;
    justify-content: center;
    padding: 0.75rem;
    font-size: 0.9rem;
  }

  .msg {
    margin-top: 1rem;
    padding: 0.75rem 1rem;
    border-radius: 10px;
    font-size: 0.85rem;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .msg-error {
    background: #fef2f2;
    color: #dc2626;
    border: 1px solid #fecaca;
  }

  .msg-success {
    background: #f0fdf4;
    color: #15803d;
    border: 1px solid #bbf7d0;
  }

  /* ════════════════════════════════════════
     PDF VIEWER
  ════════════════════════════════════════ */
  .pdf-modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.8);
    backdrop-filter: blur(4px);
    z-index: 999;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    padding: 2rem;
  }

  .pdf-modal {
    width: 100%;
    max-width: 960px;
    height: calc(100vh - 4rem);
    display: flex;
    flex-direction: column;
    background: #ffffff;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25);
  }

  .pdf-modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.5rem;
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
    flex-shrink: 0;
  }

  .pdf-modal-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: #0f172a;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .pdf-modal-actions {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  .pdf-iframe {
    flex: 1;
    width: 100%;
    border: none;
    background: #f1f5f9;
  }

  /* ════════════════════════════════════════
     QUIZ INTERFACE
  ════════════════════════════════════════ */
  .quiz-container {
    max-width: 720px;
    margin: 0 auto;
    padding-bottom: 100px;
  }

  .quiz-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
  }

  .quiz-progress {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1rem 1.25rem;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .progress-bar {
    flex: 1;
    height: 6px;
    background: #e2e8f0;
    border-radius: 999px;
    margin: 0 1rem;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #2563eb, #3b82f6);
    border-radius: 999px;
    transition: width 0.4s ease;
  }

  .progress-text {
    font-size: 0.8rem;
    font-weight: 600;
    color: #64748b;
    white-space: nowrap;
  }

  .question-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }

  .question-number {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    background: #eff6ff;
    color: #2563eb;
    border-radius: 8px;
    font-size: 0.8rem;
    font-weight: 700;
    margin-right: 0.5rem;
  }

  .question-text {
    font-weight: 700;
    font-size: 1rem;
    color: #0f172a;
    margin-bottom: 1.25rem;
    line-height: 1.5;
  }

  .quiz-options {
    display: flex;
    flex-direction: column;
    gap: 0.625rem;
  }

  .quiz-option {
    display: flex;
    align-items: center;
    gap: 0.875rem;
    padding: 0.875rem 1rem;
    border: 2px solid #e2e8f0;
    border-radius: 12px;
    background: #ffffff;
    cursor: pointer;
    text-align: left;
    font-size: 0.9rem;
    color: #475569;
    transition: all 0.2s ease;
    font-family: inherit;
    width: 100%;
  }

  .quiz-option:hover {
    border-color: #bfdbfe;
    background: #fafafa;
  }

  .quiz-option.selected {
    border-color: #2563eb;
    background: #eff6ff;
    color: #1e40af;
  }

  .quiz-key {
    width: 32px;
    height: 32px;
    border-radius: 10px;
    background: #f1f5f9;
    color: #64748b;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.85rem;
    flex-shrink: 0;
    transition: all 0.2s ease;
    border: 2px solid transparent;
  }

  .quiz-option.selected .quiz-key {
    background: #2563eb;
    color: white;
  }

  .quiz-actions {
    display: flex;
    gap: 0.75rem;
    justify-content: flex-end;
    margin-top: 1.5rem;
    position: sticky;
    bottom: 24px;
    background: rgba(248, 250, 252, 0.95);
    backdrop-filter: blur(8px);
    padding: 1rem;
    border-radius: 14px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 8px 32px rgba(0,0,0,0.08);
  }

  .quiz-result-box {
    text-align: center;
    padding: 2.5rem;
    margin-bottom: 1.5rem;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }

  .quiz-result-score {
    font-size: 3.5rem;
    font-weight: 800;
    color: #2563eb;
    letter-spacing: -0.03em;
  }

  .quiz-result-pct {
    font-size: 1.25rem;
    color: #64748b;
    margin-top: 0.5rem;
    font-weight: 600;
  }

  .quiz-feedback {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }

  .quiz-feedback-title {
    font-size: 0.9rem;
    font-weight: 700;
    color: #0f172a;
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .quiz-feedback-text {
    font-size: 0.9rem;
    color: #475569;
    line-height: 1.7;
  }

  /* ════════════════════════════════════════
     RESPONSIVE
  ════════════════════════════════════════ */
  @media (max-width: 768px) {
    .sidebar { display: none; }
    .main { padding: 1rem; }
    .stats-grid { grid-template-columns: repeat(2, 1fr); }
    .card-grid { grid-template-columns: 1fr; }
    .acard { flex-direction: column; }
    .acard-actions { width: 100%; justify-content: flex-end; }
  }
</style>

<!-- ═══════════════════════════════════════════════════════════
     HTML
═══════════════════════════════════════════════════════════ -->
<div class="dash">

  <!-- Header -->
  <header class="header">
    <div class="logo">
      <div class="header-logo">
  <img src="/favicon.png" alt="Open TutorAI" class="logo-img" />
</div>
      <span class="logo-text">Open <strong>TutorAI</strong></span>

    </div>
    {#if $user}
      <div class="user-badge">
        <div class="user-avatar">{($user.name && $user.name.charAt(0).toUpperCase()) || '?'}</div>
        <span>{$user.name}</span>
      </div>
    {/if}
  </header>

  <div class="layout">

    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-section">
        <div class="sidebar-label">Menu</div>
        {#each [
          { id: 'assignments', icon: '📋', label: 'Mes Devoirs' },
          { id: 'courses',     icon: '📚', label: 'Mes Cours'   },
          { id: 'quiz',        icon: '🧠', label: 'Mes Quiz'    },
        ] as tab}
          <button
            class="nav-item {activeTab === tab.id ? 'active' : ''}"
            on:click={() => activeTab = tab.id}
          >
            <span class="nav-icon">{tab.icon}</span>
            {tab.label}
          </button>
        {/each}
      </div>
      <hr class="nav-divider" />
      <div class="sidebar-section">
        <button class="btn-join-sidebar" on:click={() => showJoinModal = true}>
          <span class="nav-icon">➕</span>
          Rejoindre une classe
        </button>
      </div>
    </aside>

    <!-- Main -->
    <main class="main">

      {#if loading}
        <div class="spinner-container">
          <div class="spinner"></div>
          <div class="spinner-text">Chargement de vos données...</div>
        </div>

      <!-- ══════════════ DEVOIRS ══════════════ -->
      {:else if activeTab === 'assignments'}
        <div class="page-header">
          <div class="page-title-group">
            <div class="page-title">Mes Devoirs</div>
            <div class="page-sub">{assignments.length} devoir(s) à rendre</div>
          </div>
          {#if classrooms.length === 0}
            <button class="btn btn-primary" on:click={() => showJoinModal = true}>
              ➕ Rejoindre une classe
            </button>
          {/if}
        </div>

        {#if $user}
          <div class="welcome-banner">
            <div class="welcome-icon">👋</div>
            <div class="welcome-text">
              Bonjour <strong>{$user.name}</strong> — Voici vos devoirs à rendre. Bon courage !
            </div>
          </div>
        {/if}

        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">Total</span>
              <div class="stat-icon blue">📋</div>
            </div>
            <div class="stat-num">{assignments.length}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">Actifs</span>
              <div class="stat-icon green">✅</div>
            </div>
            <div class="stat-num">{assignments.filter(a => a.status === 'active').length}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">Soumis</span>
              <div class="stat-icon purple">📤</div>
            </div>
            <div class="stat-num">{assignments.filter(a => (a.submission_count || 0) > 0).length}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">Urgents</span>
              <div class="stat-icon orange">🔥</div>
            </div>
            <div class="stat-num">
              {assignments.filter(a => {
                const d = Math.ceil((new Date(a.due_date).getTime() - Date.now()) / 86400000);
                return d >= 0 && d <= 3;
              }).length}
            </div>
          </div>
        </div>

        {#if assignments.length === 0}
          <div class="empty-state">
            <div class="empty-icon">📋</div>
            <div class="empty-title">Aucun devoir</div>
            <div class="empty-desc">
              {classrooms.length === 0
                ? 'Rejoignez une classe pour voir vos devoirs.'
                : 'Aucun devoir disponible pour le moment.'}
            </div>
          </div>
        {:else}
          <div class="card-list">
            {#each assignments as a}
              <div class="card acard">
                <div class="acard-icon">📋</div>
                <div class="acard-info">
                  <div class="acard-title">{a.title}</div>
                  {#if a.description}
                    <div class="acard-desc">{a.description}</div>
                  {/if}
                  <div class="acard-meta">
                    {#if a.course}<span>📚 {a.course}</span>{/if}
                    <span>📅 {a.due_date}{a.due_time ? ' à ' + a.due_time : ''}</span>
                    <span>⭐ {a.points} pts</span>
                  </div>
                </div>
                <div class="acard-actions">
                  <span class="badge {getDaysClass(a.due_date) === 'expired' ? 'badge-red' : getDaysClass(a.due_date) === 'urgent' ? 'badge-orange' : 'badge-blue'}">
                    {getDaysLeft(a.due_date)}
                  </span>
                  <button
                    class="btn {getDaysClass(a.due_date) === 'expired' ? 'btn-secondary' : 'btn-primary'}"
                    disabled={getDaysClass(a.due_date) === 'expired'}
                  >
                    {getDaysClass(a.due_date) === 'expired' ? 'Expiré' : '📤 Soumettre'}
                  </button>
                </div>
              </div>
            {/each}
          </div>
        {/if}

      <!-- ══════════════ COURS ══════════════ -->
      {:else if activeTab === 'courses'}
        <div class="page-header">
          <div class="page-title-group">
            <div class="page-title">Mes Cours</div>
            <div class="page-sub">{courses.length} cours disponible(s)</div>
          </div>
          {#if classrooms.length === 0}
            <button class="btn btn-primary" on:click={() => showJoinModal = true}>
              ➕ Rejoindre une classe
            </button>
          {/if}
        </div>

        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">Total</span>
              <div class="stat-icon blue">📚</div>
            </div>
            <div class="stat-num">{courses.length}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">PDF</span>
              <div class="stat-icon orange">📄</div>
            </div>
            <div class="stat-num">{courses.filter(c => c.file_type === '.pdf').length}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">Modules</span>
              <div class="stat-icon purple">🗂️</div>
            </div>
            <div class="stat-num">{[...new Set(courses.map(c => c.module))].length}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">Actifs</span>
              <div class="stat-icon green">✅</div>
            </div>
            <div class="stat-num">{courses.length}</div>
          </div>
        </div>

        {#if courses.length === 0}
          <div class="empty-state">
            <div class="empty-icon">📚</div>
            <div class="empty-title">Aucun cours</div>
            <div class="empty-desc">
              {classrooms.length === 0
                ? 'Rejoignez une classe pour voir vos cours.'
                : 'Votre professeur n\'a pas encore uploadé de cours.'}
            </div>
          </div>
        {:else}
          <div class="card-grid">
            {#each courses as c}
              <div class="card ccard">
                <div class="ccard-header">
                  <div class="ccard-icon">{fileIcon(c.file_type)}</div>
                  {#if c.module}
                    <span class="badge badge-gray">{c.module}</span>
                  {/if}
                </div>
                <div class="ccard-title">{c.title}</div>
                {#if c.description}
                  <div class="ccard-desc">{c.description}</div>
                {/if}
                <div class="ccard-meta">
                  <span>📦 {formatSize(c.file_size)}</span>
                  <span>👤 {c.teacher_name || 'Enseignant'}</span>
                  {#if c.file_type}
                    <span>🗂 {c.file_type.replace('.', '').toUpperCase()}</span>
                  {/if}
                </div>
                <div class="ccard-actions">
                  {#if c.file_type === '.pdf'}
                    <button class="btn btn-outline" on:click={() => openPdf(getCourseFileUrl(c), c.title)}>
                      👁️ Lire
                    </button>
                  {/if}
                  <button class="btn btn-success" on:click={() => downloadFile(getCourseFileUrl(c), c.original_filename || c.title)}>
                    ⬇️ Télécharger
                  </button>
                </div>
              </div>
            {/each}
          </div>
        {/if}

      <!-- ══════════════ QUIZ ══════════════ -->
      {:else if activeTab === 'quiz'}
        <div class="page-header">
          <div class="page-title-group">
            <div class="page-title">🧠 Mes Quiz</div>
            <div class="page-sub">{quizzes.length} quiz disponible(s)</div>
          </div>
          {#if classrooms.length === 0}
            <button class="btn btn-primary" on:click={() => showJoinModal = true}>
              ➕ Rejoindre une classe
            </button>
          {/if}
        </div>

        {#if quizLoading}
          <div class="spinner-container">
            <div class="spinner"></div>
            <div class="spinner-text">Chargement du quiz...</div>
          </div>

        {:else if !selectedQuiz && !showQuizResults}
          {#if quizzes.length === 0}
            <div class="empty-state">
              <div class="empty-icon">🧠</div>
              <div class="empty-title">Aucun quiz</div>
              <div class="empty-desc">
                {classrooms.length === 0
                  ? 'Rejoignez une classe pour voir vos quiz.'
                  : 'Aucun quiz disponible pour le moment.'}
              </div>
            </div>
          {:else}
            <div class="stats-grid">
              <div class="stat-card">
                <div class="stat-header">
                  <span class="stat-label">Total</span>
                  <div class="stat-icon blue">🧠</div>
                </div>
                <div class="stat-num">{quizzes.length}</div>
              </div>
              <div class="stat-card">
                <div class="stat-header">
                  <span class="stat-label">Passés</span>
                  <div class="stat-icon green">✅</div>
                </div>
                <div class="stat-num">{passedCount}</div>
              </div>
              <div class="stat-card">
                <div class="stat-header">
                  <span class="stat-label">À faire</span>
                  <div class="stat-icon orange">📝</div>
                </div>
                <div class="stat-num">{todoCount}</div>
              </div>
            </div>

            <div class="card-grid">
              {#each quizzes as quiz}
                <div class="card qcard">
                  <div class="qcard-header">
                    <div class="qcard-icon">🧠</div>
                    <span class="badge {quiz.status === 'published' ? 'badge-green' : 'badge-gray'}">
                      {quiz.status === 'published' ? 'Publié' : 'Brouillon'}
                    </span>
                  </div>
                  <div class="qcard-title">{quiz.title}</div>
                  <div class="qcard-meta">
                    <span>📚 {quiz.course_title || 'Général'}</span>
                    <span>❓ {quiz.question_count || 0} questions</span>
                  </div>

                  {#if quiz.already_submitted && quiz.submission}
                    <div class="qcard-result">
                      <div class="qcard-result-score">✅ Score: {quiz.submission.score_pct}%</div>
                      {#if quiz.submission.ai_note}
                        <div class="qcard-result-note">🤖 Note: {quiz.submission.ai_note}/20</div>
                      {/if}
                      {#if quiz.submission.ai_feedback}
                        <div class="qcard-result-feedback">{quiz.submission.ai_feedback}</div>
                      {/if}
                    </div>
                  {:else}
                    <div class="qcard-actions">
                      <button class="btn btn-primary" on:click={() => startQuiz(quiz)}>
                        🚀 Passer le quiz
                      </button>
                    </div>
                  {/if}
                </div>
              {/each}
            </div>
          {/if}

        {:else if selectedQuiz}
          <div class="quiz-container">
            <div class="quiz-header">
              <div class="page-title">{selectedQuiz.title}</div>
              <button class="btn btn-secondary" on:click={() => selectedQuiz = null}>Annuler</button>
            </div>

            <div class="quiz-progress">
              <span class="progress-text">Progression</span>
              <div class="progress-bar">
                <div class="progress-fill" style="width: {(Object.keys(currentAnswers).length / selectedQuiz.questions.length) * 100}%"></div>
              </div>
              <span class="progress-text">{Object.keys(currentAnswers).length}/{selectedQuiz.questions.length}</span>
            </div>

            {#each selectedQuiz.questions as q, i}
              <div class="question-card">
                <div class="question-text">
                  <span class="question-number">{i + 1}</span>
                  {q.question}
                </div>
                <div class="quiz-options">
                  {#each Object.entries(q.options || {}) as [key, val]}
                    {#if val}
                      <button
                        class="quiz-option {currentAnswers[q.id] === key ? 'selected' : ''}"
                        on:click={() => selectAnswer(q.id, key)}
                      >
                        <span class="quiz-key">{key}</span>
                        {val}
                      </button>
                    {/if}
                  {/each}
                </div>
              </div>
            {/each}

            <div class="quiz-actions">
              <button class="btn btn-secondary" on:click={() => selectedQuiz = null}>Annuler</button>
              <button
                class="btn btn-primary"
                on:click={submitQuiz}
                disabled={Object.keys(currentAnswers).length !== selectedQuiz.questions.length}
              >
                Soumettre ({Object.keys(currentAnswers).length}/{selectedQuiz.questions.length})
              </button>
            </div>
          </div>

        {:else if showQuizResults}
          <div style="max-width: 600px; margin: 0 auto;">
            <button class="btn btn-secondary" style="margin-bottom: 1.5rem;" on:click={() => showQuizResults = null}>
              ← Retour aux quiz
            </button>

            <div class="quiz-result-box">
              <div class="quiz-result-score">{showQuizResults.score}/{showQuizResults.total}</div>
              <div class="quiz-result-pct">{showQuizResults.score_pct}% de réussite</div>
            </div>

            {#if showQuizResults.ai_feedback}
              <div class="quiz-feedback">
                <div class="quiz-feedback-title">🤖 Feedback IA</div>
                <div class="quiz-feedback-text">{showQuizResults.ai_feedback}</div>
              </div>
            {/if}
          </div>
        {/if}
      {/if}

    </main>
  </div>
</div>

<!-- ══════════════ MODAL Rejoindre ══════════════ -->
{#if showJoinModal}
  <div class="modal-backdrop" on:click|self={() => { showJoinModal = false; joinError = ''; joinCode = ''; }}>
    <div class="modal">
      <div class="modal-icon">🏫</div>
      <div class="modal-title">Rejoindre une classe</div>
      <div class="modal-sub">Entrez le code à 6 caractères donné par votre professeur pour accéder à la classe.</div>

      <input
        class="code-input"
        type="text"
        bind:value={joinCode}
        placeholder="AB3K9Z"
        maxlength="10"
        on:keydown={(e) => e.key === 'Enter' && joinClassroom()}
      />

      {#if joinError}
        <div class="msg msg-error">❌ {joinError}</div>
      {/if}
      {#if joinSuccess}
        <div class="msg msg-success">✅ {joinSuccess}</div>
      {/if}

      <div class="modal-actions">
        <button class="btn btn-secondary" on:click={() => { showJoinModal = false; joinError = ''; joinCode = ''; }}>
          Annuler
        </button>
        <button class="btn btn-primary" on:click={joinClassroom} disabled={joinLoading}>
          {joinLoading ? '⏳ En cours...' : 'Rejoindre'}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- ══════════════ MODAL PDF ══════════════ -->
{#if selectedPdf}
  <div class="pdf-modal-backdrop" on:click|self={closePdf}>
    <div class="pdf-modal">
      <div class="pdf-modal-header">
        <div class="pdf-modal-title">📄 {selectedPdf.title}</div>
        <div class="pdf-modal-actions">
          <button class="btn btn-success" on:click={() => downloadFile(selectedPdf.url, selectedPdf.title + '.pdf')}>
            ⬇️ Télécharger
          </button>
          <button class="btn btn-secondary" on:click={closePdf}>✕ Fermer</button>
        </div>
      </div>
      <iframe class="pdf-iframe" src="{selectedPdf.url}#toolbar=1&navpanes=0" title={selectedPdf.title}></iframe>
    </div>
  </div>
{/if}