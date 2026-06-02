<script>
  import { goto } from '$app/navigation';
  import { user } from '$lib/stores';
  import { onMount, getContext } from 'svelte';

  let loading = true;
  let error = null;
  const i18n = getContext('i18n');

  onMount(async () => {
    try {
      loading = true;
      if (!$user) {
        await goto('/auth');
        return;
      }
      if ($user.role !== 'user') {
        await goto(`/${$user.role}`);
        return;
      } else {
        await goto(`/student/dashboard`);
      }
      loading = false;
    } catch (err) {
      error = err.message || 'An error occurred';
      loading = false;
    }
  });
</script>