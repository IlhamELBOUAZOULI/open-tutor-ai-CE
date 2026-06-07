<script>
  import { goto } from '$app/navigation';
  import { user } from '$lib/stores';
  import { onMount } from 'svelte';

  onMount(async () => {
    if (!$user) { goto('/auth'); return; }
    if ($user.role !== 'user') { goto(`/${$user.role}`); return; }
    goto('/student/dashboard');
  });
</script>