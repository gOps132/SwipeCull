// User Settings Screen JS
document.addEventListener('DOMContentLoaded', () => {
    // Live preview: toggle dark mode as soon as the checkbox changes.
    // The choice is only persisted when the form is saved; the server renders
    // the saved value on the next page load.
    const darkToggle = document.getElementById('id_dark_mode');
    if (darkToggle) {
        darkToggle.addEventListener('change', () => {
            document.documentElement.classList.toggle('dark', darkToggle.checked);
        });
    }
});
