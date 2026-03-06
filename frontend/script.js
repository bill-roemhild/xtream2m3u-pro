// State Management
const DEFAULT_CREDENTIALS = {
    url: '',
    username: '',
    password: ''
};

let state = {
    categories: [],
    streams: [],
    currentStep: 1,
    filterMode: 'include',
    selectedCategories: new Set(),
    selectedChannelIds: new Set(),
    collapsedSections: new Set(),
    searchTerm: '',
    channelSearchTerm: '',
    channelEditorCategory: null,
    credentials: {
        url: '',
        username: '',
        password: '',
        includeVod: false
    },
    subscription: null,
    credentialProfiles: [],
    activeProfileKey: '',
    profileModalMode: 'new',
    lastGeneratedConfig: null,
    pendingDelete: null,
    playlistModalMode: 'create',
    editingPlaylistId: null,
    editingPlaylistOwner: '',
    authenticated: false,
    currentUsername: '',
    isAdmin: false,
    lastAuthErrorTs: 0,
    appInitialized: false
};
let channelViewerHls = null;
const VIEWER_VOLUME_KEY = 'channel_viewer_volume';

// DOM Elements
const elements = {
    steps: {
        1: document.getElementById('step1'),
        2: document.getElementById('step2'),
        3: document.getElementById('step3')
    },
    loading: document.getElementById('loading'),
    loadingText: document.getElementById('loadingText'),
    categoryChips: document.getElementById('categoryChips'),
    selectionCounter: document.getElementById('selectionCounter'),
    selectionText: document.getElementById('selectionText'),
    confirmationModal: document.getElementById('confirmationModal'),
    deleteConfirmModal: document.getElementById('deleteConfirmModal'),
    deleteConfirmText: document.getElementById('deleteConfirmText'),
    warningModal: document.getElementById('warningModal'),
    warningModalText: document.getElementById('warningModalText'),
    modalSummary: document.getElementById('modalSummary'),
    results: document.getElementById('results'),
    downloadLink: document.getElementById('finalDownloadLink'),
    searchInput: document.getElementById('categorySearch'),
    apiBuilderModal: document.getElementById('apiBuilderModal'),
    playlistBuilderModal: document.getElementById('playlistBuilderModal'),
    channelEditorModal: document.getElementById('channelEditorModal'),
    channelEditorTitle: document.getElementById('channelEditorTitle'),
    channelSearchInput: document.getElementById('channelSearchInput'),
    channelList: document.getElementById('channelList'),
    channelSelectionCounter: document.getElementById('channelSelectionCounter'),
    channelSelectionText: document.getElementById('channelSelectionText'),
    channelViewerModal: document.getElementById('channelViewerModal'),
    channelViewerTitle: document.getElementById('channelViewerTitle'),
    channelViewerVideo: document.getElementById('channelViewerVideo'),
    channelViewerPlayBtn: document.getElementById('channelViewerPlayBtn'),
    channelViewerMuteBtn: document.getElementById('channelViewerMuteBtn'),
    channelViewerVolume: document.getElementById('channelViewerVolume'),
    channelViewerStatus: document.getElementById('channelViewerStatus'),
    playlistBuilderName: document.getElementById('playlistBuilderName'),
    playlistBuilderTitle: document.getElementById('playlistBuilderTitle'),
    playlistBuilderSaveBtn: document.getElementById('playlistBuilderSaveBtn'),
    newProfileModal: document.getElementById('newProfileModal'),
    generatedApiUrl: document.getElementById('generatedApiUrl'),
    subscriptionDetails: document.getElementById('subscriptionDetails'),
    profileSelect: document.getElementById('credentialProfileSelect'),
    savedPlaylistsList: document.getElementById('savedPlaylistsList'),
    modalPlaylistName: document.getElementById('modalPlaylistName'),
    modalSavedLinks: document.getElementById('modalSavedLinks'),
    modalSavedM3uUrl: document.getElementById('modalSavedM3uUrl'),
    modalSavedXmltvUrl: document.getElementById('modalSavedXmltvUrl'),
    newProfileBtn: document.getElementById('newProfileBtn'),
    editProfileBtn: document.getElementById('editProfileBtn'),
    deleteProfileBtn: document.getElementById('deleteProfileBtn'),
    authModal: document.getElementById('authModal'),
    authModalTitle: document.getElementById('authModalTitle'),
    authModalSubtitle: document.getElementById('authModalSubtitle'),
    authSetupForm: document.getElementById('authSetupForm'),
    authLoginForm: document.getElementById('authLoginForm'),
    authError: document.getElementById('authError'),
    authLoginSubmitBtn: document.getElementById('authLoginSubmitBtn'),
    addUserBtn: document.getElementById('addUserBtn'),
    backupRestoreBtn: document.getElementById('backupRestoreBtn'),
    logoutBtn: document.getElementById('logoutBtn'),
    authUserBadge: document.getElementById('authUserBadge'),
    addUserModal: document.getElementById('addUserModal'),
    authUsersList: document.getElementById('authUsersList'),
    backupModal: document.getElementById('backupModal')
};

function getCurrentFormCredentials() {
    return {
        url: document.getElementById('url').value.trim(),
        username: document.getElementById('username').value.trim(),
        password: document.getElementById('password').value.trim()
    };
}

function applyCredentialsToForm(credentials) {
    document.getElementById('url').value = credentials.url || '';
    document.getElementById('username').value = credentials.username || '';
    document.getElementById('password').value = credentials.password || '';
    document.getElementById('includeVod').checked = Boolean(credentials.includeVod);
}

function getDefaultProfile() {
    return null;
}

function sanitizeProfiles(rawProfiles) {
    if (!Array.isArray(rawProfiles)) return [];

    const seenKeys = new Set();
    const cleaned = [];
    rawProfiles.forEach((profile) => {
        if (!profile || typeof profile !== 'object') return;
        const name = String(profile.name || '').trim();
        const owner = String(profile.owner || '').trim();
        const url = String(profile.url || '').trim();
        const username = String(profile.username || '').trim();
        const password = String(profile.password || '');
        const key = `${owner}::${name}`;
        if (!name || seenKeys.has(key)) return;
        seenKeys.add(key);
        const includeVod = Boolean(profile.includeVod ?? profile.include_vod);
        cleaned.push({ name, owner, url, username, password, includeVod });
    });

    return cleaned;
}

function getProfileKey(profile) {
    return `${String(profile?.owner || '').trim()}::${String(profile?.name || '').trim()}`;
}

function getProfileLabel(profile) {
    const name = String(profile?.name || '').trim();
    const owner = String(profile?.owner || '').trim();
    return owner ? `${name} (${owner})` : name;
}

async function loadProfilesFromServer() {
    try {
        const response = await fetch('/profiles');
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.details || payload.error || 'Failed to load profiles');
        }
        state.credentialProfiles = sanitizeProfiles(payload.profiles);
        console.info('[profiles] loaded from container', {
            count: state.credentialProfiles.length,
            storePath: payload.store_path
        });
    } catch (error) {
        console.warn('[profiles] failed loading from server, using defaults', error);
        state.credentialProfiles = [];
    }
}

function updateConnectionAvailability() {
    const loadBtn = document.getElementById('loadBtn');
    if (!loadBtn) return;
    // Keep Connect available after login so validation feedback is shown on click.
    loadBtn.disabled = !state.authenticated;
}

function renderAuthControls() {
    const username = String(state.currentUsername || '').trim();
    if (elements.authUserBadge) {
        if (state.authenticated && username) {
            elements.authUserBadge.style.display = 'inline-flex';
            elements.authUserBadge.textContent = state.isAdmin ? `${username} (admin)` : username;
        } else {
            elements.authUserBadge.style.display = 'none';
            elements.authUserBadge.textContent = '';
        }
    }
    if (elements.logoutBtn) {
        elements.logoutBtn.style.display = state.authenticated ? 'inline-flex' : 'none';
    }
    if (elements.addUserBtn) {
        elements.addUserBtn.style.display = state.authenticated && state.isAdmin ? 'inline-flex' : 'none';
    }
    if (elements.backupRestoreBtn) {
        elements.backupRestoreBtn.style.display = state.authenticated && state.isAdmin ? 'inline-flex' : 'none';
    }
}

function showAuthModal({ needsSetup }) {
    if (!elements.authModal) return;
    elements.authModal.classList.add('active');
    if (needsSetup) {
        if (elements.authModalTitle) elements.authModalTitle.textContent = 'Create Admin Account';
        if (elements.authModalSubtitle) elements.authModalSubtitle.textContent = 'First-time setup: create the initial admin user.';
        if (elements.authSetupForm) elements.authSetupForm.style.display = 'block';
        if (elements.authLoginForm) elements.authLoginForm.style.display = 'none';
        if (elements.authLoginSubmitBtn) elements.authLoginSubmitBtn.style.display = 'none';
    } else {
        if (elements.authModalTitle) elements.authModalTitle.textContent = 'Login Required';
        if (elements.authModalSubtitle) elements.authModalSubtitle.textContent = 'Sign in to access playlists and APIs.';
        if (elements.authSetupForm) elements.authSetupForm.style.display = 'none';
        if (elements.authLoginForm) elements.authLoginForm.style.display = 'block';
        if (elements.authLoginSubmitBtn) elements.authLoginSubmitBtn.style.display = 'inline-flex';
    }
    clearAuthError();
    renderAuthControls();
}

function hideAuthModal() {
    if (elements.authModal) elements.authModal.classList.remove('active');
    clearAuthError();
}

function showAuthError(message) {
    if (!elements.authError) {
        showError(message);
        return;
    }
    elements.authError.textContent = message;
    elements.authError.style.display = 'flex';
}

function clearAuthError() {
    if (!elements.authError) return;
    elements.authError.textContent = '';
    elements.authError.style.display = 'none';
}

async function getAuthStatus() {
    const response = await fetch('/auth/status');
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.details || data.error || 'Failed to check auth status');
    }
    return data;
}

async function submitAuthSetup() {
    const username = (document.getElementById('setupUsername')?.value || '').trim();
    const password = document.getElementById('setupPassword')?.value || '';
    if (!username || !password) {
        showAuthError('Setup requires username and password.');
        return;
    }
    try {
        const response = await fetch('/auth/setup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.details || data.error || 'Failed to create admin account');
        }
        state.authenticated = true;
        state.currentUsername = data.username || '';
        state.isAdmin = Boolean(data.is_admin);
        renderAuthControls();
        hideAuthModal();
        await initializeApp();
    } catch (error) {
        console.error('[submitAuthSetup] failed', error);
        showAuthError(error.message);
    }
}

async function submitAuthLogin() {
    const username = (document.getElementById('loginUsername')?.value || '').trim();
    const password = document.getElementById('loginPassword')?.value || '';
    if (!username || !password) {
        showAuthError('Login requires username and password.');
        return;
    }
    try {
        const response = await fetch('/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.details || data.error || 'Login failed');
        }
        state.authenticated = true;
        state.currentUsername = data.username || '';
        state.isAdmin = Boolean(data.is_admin);
        renderAuthControls();
        hideAuthModal();
        await initializeApp();
    } catch (error) {
        console.error('[submitAuthLogin] failed', error);
        showAuthError(error.message);
    }
}

async function initializeApp() {
    if (state.appInitialized) {
        updateConnectionAvailability();
        return;
    }
    await loadProfilesFromServer();
    renderProfileSelect();
    applyActiveProfileToForm();
    await loadSavedPlaylistsList();
    updateConnectionAvailability();
    state.appInitialized = true;
}

function renderProfileSelect() {
    if (!elements.profileSelect) return;

    if (state.credentialProfiles.length === 0) {
        elements.profileSelect.innerHTML = '<option value="">No saved servers</option>';
        elements.profileSelect.value = '';
        elements.profileSelect.disabled = true;
        if (elements.editProfileBtn) elements.editProfileBtn.disabled = true;
        if (elements.deleteProfileBtn) elements.deleteProfileBtn.disabled = true;
        state.activeProfileKey = '';
        updateConnectionAvailability();
        return;
    }
    elements.profileSelect.disabled = false;
    if (elements.editProfileBtn) elements.editProfileBtn.disabled = false;
    if (elements.deleteProfileBtn) elements.deleteProfileBtn.disabled = false;
    const optionsHtml = state.credentialProfiles
        .map(profile => `<option value="${escapeHtml(getProfileKey(profile))}">${escapeHtml(getProfileLabel(profile))}</option>`)
        .join('');
    elements.profileSelect.innerHTML = optionsHtml;

    if (!state.credentialProfiles.some(p => getProfileKey(p) === state.activeProfileKey)) {
        state.activeProfileKey = getProfileKey(state.credentialProfiles[0]);
    }
    elements.profileSelect.value = state.activeProfileKey;
    updateConnectionAvailability();
}

function applyActiveProfileToForm() {
    const profile = state.credentialProfiles.find(p => getProfileKey(p) === state.activeProfileKey) || state.credentialProfiles[0];
    if (!profile) {
        applyCredentialsToForm(DEFAULT_CREDENTIALS);
        state.activeProfileKey = '';
        updateConnectionAvailability();
        return;
    }
    state.activeProfileKey = getProfileKey(profile);
    applyCredentialsToForm(profile);
    if (elements.profileSelect) {
        elements.profileSelect.value = getProfileKey(profile);
    }
    updateConnectionAvailability();
}

function getActiveProfile() {
    return state.credentialProfiles.find(p => getProfileKey(p) === state.activeProfileKey) || null;
}

async function persistProfile(profile) {
    const response = await fetch('/profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profile)
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.details || payload.error || 'Failed to save profile');
    }
    state.credentialProfiles = sanitizeProfiles(payload.profiles);
}

async function removeProfile(name) {
    const profile = state.credentialProfiles.find((p) => p.name === name && getProfileKey(p) === state.activeProfileKey);
    const response = await fetch('/profiles/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, owner: profile?.owner || '' })
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.details || payload.error || 'Failed to delete profile');
    }
    state.credentialProfiles = sanitizeProfiles(payload.profiles);
}

async function createNewProfile() {
    if (!elements.newProfileModal) return;
    state.profileModalMode = 'new';
    const header = elements.newProfileModal.querySelector('.modal-header h3');
    if (header) header.textContent = 'Add New Server';
    document.getElementById('newProfileName').value = '';
    document.getElementById('newProfileName').readOnly = false;
    document.getElementById('newProfileUrl').value = '';
    document.getElementById('newProfileUsername').value = '';
    document.getElementById('newProfilePassword').value = '';
    document.getElementById('newProfileIncludeVod').checked = false;
    elements.newProfileModal.classList.add('active');
}

function editCurrentProfile() {
    if (!elements.newProfileModal) return;
    const activeProfile = state.credentialProfiles.find(p => getProfileKey(p) === state.activeProfileKey);
    if (!activeProfile) {
        showError('No active profile selected.');
        return;
    }
    state.profileModalMode = 'edit';
    const header = elements.newProfileModal.querySelector('.modal-header h3');
    if (header) header.textContent = 'Edit Server';
    document.getElementById('newProfileName').value = activeProfile.name;
    document.getElementById('newProfileName').readOnly = true;
    document.getElementById('newProfileUrl').value = activeProfile.url || '';
    document.getElementById('newProfileUsername').value = activeProfile.username || '';
    document.getElementById('newProfilePassword').value = activeProfile.password || '';
    document.getElementById('newProfileIncludeVod').checked = Boolean(activeProfile.includeVod);
    elements.newProfileModal.classList.add('active');
}

function closeNewProfileModal() {
    if (!elements.newProfileModal) return;
    elements.newProfileModal.classList.remove('active');
}

function openAddUserModal() {
    if (!state.isAdmin) {
        showError('Admin privileges required.');
        return;
    }
    if (!elements.addUserModal) return;
    const usernameEl = document.getElementById('addUserUsername');
    const passwordEl = document.getElementById('addUserPassword');
    const isAdminEl = document.getElementById('addUserIsAdmin');
    if (usernameEl) usernameEl.value = '';
    if (passwordEl) passwordEl.value = '';
    if (isAdminEl) isAdminEl.checked = false;
    elements.addUserModal.classList.add('active');
    loadAuthUsers();
}

function closeAddUserModal() {
    if (elements.addUserModal) {
        elements.addUserModal.classList.remove('active');
    }
}

function openBackupModal() {
    if (!state.isAdmin) {
        showError('Admin privileges required.');
        return;
    }
    if (!elements.backupModal) return;
    const fileEl = document.getElementById('backupFileInput');
    if (fileEl) fileEl.value = '';
    elements.backupModal.classList.add('active');
}

function closeBackupModal() {
    if (!elements.backupModal) return;
    elements.backupModal.classList.remove('active');
}

async function downloadBackup() {
    if (!state.isAdmin) {
        showError('Admin privileges required.');
        return;
    }
    try {
        const response = await fetch('/backup/download');
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.details || err.error || 'Failed to download backup');
        }
        const blob = await response.blob();
        const disposition = response.headers.get('content-disposition') || '';
        const filenameMatch = disposition.match(/filename=\"?([^\";]+)\"?/i);
        const filename = filenameMatch?.[1] || 'xtream2m3u-backup.json';
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
        showSuccess('Backup downloaded.');
    } catch (error) {
        console.error('[downloadBackup] failed', error);
        showError(error.message);
    }
}

async function restoreBackup() {
    if (!state.isAdmin) {
        showError('Admin privileges required.');
        return;
    }
    const fileEl = document.getElementById('backupFileInput');
    const file = fileEl?.files?.[0];
    if (!file) {
        showError('Choose a backup file first.');
        return;
    }

    try {
        const formData = new FormData();
        formData.append('file', file);
        const response = await fetch('/backup/restore', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.details || data.error || 'Failed to restore backup');
        }

        closeBackupModal();
        if (data.relogin_required) {
            showSuccess('Backup restored. Please log in again.');
            resetAppForLoggedOutState();
            showAuthModal({ needsSetup: false });
            return;
        }

        state.authenticated = true;
        state.isAdmin = true;
        renderAuthControls();
        state.appInitialized = false;
        await initializeApp();
        showSuccess(
            `Backup restored: ${data.restored?.users || 0} users, ${data.restored?.profiles || 0} services, ${data.restored?.saved_playlists || 0} playlists.`
        );
    } catch (error) {
        console.error('[restoreBackup] failed', error);
        showError(error.message);
    }
}

async function submitAddUser() {
    if (!state.isAdmin) {
        showError('Admin privileges required.');
        return;
    }
    const username = (document.getElementById('addUserUsername')?.value || '').trim();
    const password = document.getElementById('addUserPassword')?.value || '';
    const isAdmin = Boolean(document.getElementById('addUserIsAdmin')?.checked);

    if (!username || !password) {
        showError('Username and password are required.');
        return;
    }
    if (password.length < 8) {
        showError('Password must be at least 8 characters.');
        return;
    }

    try {
        const response = await fetch('/auth/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, is_admin: isAdmin })
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.details || data.error || 'Failed to create user');
        }
        closeAddUserModal();
        showSuccess(`User "${data.username}" created.`);
        loadAuthUsers();
    } catch (error) {
        console.error('[submitAddUser] failed', error);
        showError(error.message);
    }
}

async function loadAuthUsers() {
    if (!state.isAdmin || !elements.authUsersList) return;
    try {
        const response = await fetch('/auth/users');
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.details || data.error || 'Failed to load users');
        }
        const users = Array.isArray(data.users) ? data.users : [];
        if (users.length === 0) {
            elements.authUsersList.innerHTML = '<div class="saved-playlist-item">No users found.</div>';
            return;
        }

        elements.authUsersList.innerHTML = users.map((user) => {
            const username = String(user.username || '').trim();
            const isSelf = username === state.currentUsername;
            const role = user.is_admin ? 'Admin' : 'User';
            const encodedUsername = encodeURIComponent(username);
            return `
                <div class="saved-playlist-item">
                    <div class="saved-playlist-main">
                        <strong>${escapeHtml(username)}</strong>
                        <small>Role: ${escapeHtml(role)}</small>
                    </div>
                    <div style="display:flex; gap:0.35rem;">
                        <button
                            class="btn-copy"
                            type="button"
                            title="${isSelf ? 'You cannot delete your own account' : 'Delete user and related services/playlists'}"
                            ${isSelf ? 'disabled style="opacity:0.5;cursor:not-allowed;"' : `onclick="deleteAuthUser(decodeURIComponent('${encodedUsername}'))"`}
                        >🗑️</button>
                    </div>
                </div>
            `;
        }).join('');
    } catch (error) {
        console.error('[loadAuthUsers] failed', error);
        elements.authUsersList.innerHTML = '<div class="saved-playlist-item">Failed to load users.</div>';
    }
}

function deleteAuthUser(username) {
    const name = String(username || '').trim();
    if (!name) return;
    state.pendingDelete = { type: 'auth_user', id: name };
    openDeleteConfirmModal(`Delete user "${name}" and all related services/playlists?`);
}

async function executeDeleteAuthUser(username) {
    const name = String(username || '').trim();
    if (!name) return;
    try {
        const response = await fetch('/auth/users/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: name })
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.details || data.error || 'Failed to delete user');
        }
        showSuccess(`Deleted "${name}" (${data.deleted_profiles || 0} services, ${data.deleted_playlists || 0} playlists removed).`);
        await loadAuthUsers();
        await loadProfilesFromServer();
        renderProfileSelect();
        applyActiveProfileToForm();
        await loadSavedPlaylistsList();
    } catch (error) {
        console.error('[executeDeleteAuthUser] failed', error);
        showError(error.message);
    }
}

function resetAppForLoggedOutState() {
    state.authenticated = false;
    state.currentUsername = '';
    state.isAdmin = false;
    state.appInitialized = false;
    state.categories = [];
    state.subscription = null;
    state.credentialProfiles = [];
    state.activeProfileKey = '';
    state.selectedCategories = new Set();
    state.collapsedSections = new Set();
    renderProfileSelect();
    applyActiveProfileToForm();
    renderSubscriptionDetails();
    if (elements.savedPlaylistsList) {
        elements.savedPlaylistsList.innerHTML = '<div class="saved-playlist-item">Login required.</div>';
    }
    showStep(1);
    updateConnectionAvailability();
    renderAuthControls();
}

async function submitLogout() {
    try {
        await fetch('/auth/logout', { method: 'POST' });
    } catch (error) {
        console.warn('[submitLogout] request failed', error);
    } finally {
        closeAddUserModal();
        resetAppForLoggedOutState();
        showAuthModal({ needsSetup: false });
    }
}

async function saveNewProfileFromModal() {
    const name = document.getElementById('newProfileName').value.trim();
    const url = document.getElementById('newProfileUrl').value.trim();
    const username = document.getElementById('newProfileUsername').value.trim();
    const password = document.getElementById('newProfilePassword').value.trim();
    const includeVod = document.getElementById('newProfileIncludeVod').checked;

    if (!name || !url || !username || !password) {
        showError('Please fill all new server fields.');
        return;
    }
    if (state.profileModalMode === 'new' && state.credentialProfiles.some(p => p.name === name && p.owner === state.currentUsername)) {
        showError(`A profile named "${name}" already exists.`);
        return;
    }

    try {
        const activeProfile = state.credentialProfiles.find(p => getProfileKey(p) === state.activeProfileKey);
        const targetOwner = state.profileModalMode === 'edit' ? (activeProfile?.owner || '') : state.currentUsername;
        await persistProfile({
            name,
            url,
            username,
            password,
            include_vod: includeVod,
            owner: state.profileModalMode === 'edit' ? targetOwner : ''
        });
        const selected = state.credentialProfiles.find(
            (p) => p.name === name && p.url === url && p.username === username && (!targetOwner || p.owner === targetOwner)
        ) || state.credentialProfiles[0];
        state.activeProfileKey = selected ? getProfileKey(selected) : '';
        renderProfileSelect();
        applyActiveProfileToForm();
        closeNewProfileModal();
        console.info('[profiles] profile saved', { mode: state.profileModalMode, name });
    } catch (error) {
        console.error('[profiles] save failed', error);
        showError(error.message);
    }
}

async function deleteCurrentProfile() {
    const activeProfile = state.credentialProfiles.find(p => getProfileKey(p) === state.activeProfileKey);
    const name = activeProfile?.name || '';
    if (!name) return;
    state.pendingDelete = { type: 'profile', id: name };
    openDeleteConfirmModal(`Delete profile "${getProfileLabel(activeProfile)}"?`);
}

async function executeDeleteCurrentProfile(name) {
    try {
        await removeProfile(name);
        state.activeProfileKey = state.credentialProfiles[0] ? getProfileKey(state.credentialProfiles[0]) : '';
        renderProfileSelect();
        applyActiveProfileToForm();
        console.info('[profiles] deleted profile', { name });
    } catch (error) {
        console.error('[profiles] delete failed', error);
        showError(error.message);
    }
}

function onProfileChanged(key) {
    state.activeProfileKey = key;
    applyActiveProfileToForm();
    loadSavedPlaylistsList();
    console.info('[profiles] switched profile', { key });
}

// Step Navigation
function showStep(stepNumber) {
    // Hide all steps
    Object.values(elements.steps).forEach(step => step.classList.remove('active'));
    // Show target step
    elements.steps[stepNumber].classList.add('active');
    state.currentStep = stepNumber;
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function goBackToStep1() {
    showStep(1);
}

function showLoading(message = 'Loading...') {
    // Hide all steps
    Object.values(elements.steps).forEach(step => step.classList.remove('active'));
    elements.loading.style.display = 'block';
    elements.loadingText.textContent = message;
}

function hideLoading() {
    elements.loading.style.display = 'none';
}

function showError(message) {
    const normalized = String(message || '').toLowerCase();
    const isAuthError = normalized.includes('login required') || normalized.includes('unauthorized');
    if (isAuthError) {
        const now = Date.now();
        if (now - state.lastAuthErrorTs > 2000) {
            state.lastAuthErrorTs = now;
            state.authenticated = false;
            updateConnectionAvailability();
            renderAuthControls();
            showAuthModal({ needsSetup: false });
        }
        return;
    }

    elements.results.innerHTML = `
        <div class="alert alert-error">
            <span>⚠️</span> ${message}
        </div>
    `;
    setTimeout(() => {
        elements.results.innerHTML = '';
    }, 5000);
}

function showSuccess(message) {
    elements.results.innerHTML = `
        <div class="alert alert-success">
            <span>✓</span> ${message}
        </div>
    `;
    setTimeout(() => {
        elements.results.innerHTML = '';
    }, 4000);
}

function formatUnixTimestamp(timestamp) {
    if (!timestamp) return 'N/A';
    const parsed = Number(timestamp);
    if (!Number.isFinite(parsed) || parsed <= 0) return 'N/A';
    return new Date(parsed * 1000).toLocaleString();
}

function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function trialText(isTrial) {
    return String(isTrial) === '1' ? 'Yes' : 'No';
}

function normalizeStreamId(stream) {
    const value = stream?.stream_id ?? stream?.series_id ?? '';
    return String(value).trim();
}

function getCategoryStreams(category) {
    if (!category) return [];
    const categoryId = String(category.category_id ?? '').trim();
    const type = String(category.content_type || 'live').trim();
    return state.streams.filter((stream) => {
        const streamCategoryId = String(stream?.category_id ?? '').trim();
        const streamType = String(stream?.content_type || 'live').trim();
        return streamCategoryId === categoryId && streamType === type;
    });
}

function getSelectedChannelCountForCategory(category) {
    return getCategoryStreams(category).reduce((acc, stream) => {
        const streamId = normalizeStreamId(stream);
        return acc + (streamId && state.selectedChannelIds.has(streamId) ? 1 : 0);
    }, 0);
}

function syncSelectedCategoriesFromChannels() {
    const next = new Set();
    state.categories.forEach((category) => {
        if (getSelectedChannelCountForCategory(category) > 0) {
            next.add(String(category.category_name || '').trim());
        }
    });
    state.selectedCategories = next;
}

function renderSubscriptionDetails() {
    const details = state.subscription;
    if (!details || !elements.subscriptionDetails) {
        if (elements.subscriptionDetails) {
            elements.subscriptionDetails.innerHTML = '';
        }
        return;
    }

    const profile = details.profile || {};
    const server = details.server || {};

    const statusClass = String(profile.status || details.status || '').toLowerCase() === 'active'
        ? 'subscription-status-active'
        : 'subscription-status-inactive';

    const formats = Array.isArray(profile.allowed_output_formats || details.allowed_output_formats)
        && (profile.allowed_output_formats || details.allowed_output_formats).length > 0
        ? (profile.allowed_output_formats || details.allowed_output_formats).join(', ')
        : 'N/A';

    elements.subscriptionDetails.innerHTML = `
        <div class="subscription-card">
            <h3>Subscription Details</h3>
            <div class="subscription-grid">
                <div class="subscription-row"><span class="subscription-label">Status</span><span class="subscription-value ${statusClass}">${escapeHtml(profile.status || details.status || 'Unknown')}</span></div>
                <div class="subscription-row"><span class="subscription-label">Expires</span><span class="subscription-value">${escapeHtml(formatUnixTimestamp(profile.exp_date || details.exp_date))}</span></div>
                <div class="subscription-row"><span class="subscription-label">Created</span><span class="subscription-value">${escapeHtml(formatUnixTimestamp(profile.created_at || details.created_at))}</span></div>
                <div class="subscription-row"><span class="subscription-label">Trial</span><span class="subscription-value">${escapeHtml(trialText(profile.is_trial ?? details.is_trial))}</span></div>
                <div class="subscription-row"><span class="subscription-label">Connections</span><span class="subscription-value">${escapeHtml(profile.active_cons ?? details.active_cons ?? '0')} / ${escapeHtml(profile.max_connections ?? details.max_connections ?? '0')}</span></div>
                <div class="subscription-row"><span class="subscription-label">Allowed Formats</span><span class="subscription-value">${escapeHtml(formats)}</span></div>
                <div class="subscription-row"><span class="subscription-label">Server URL</span><span class="subscription-value">${escapeHtml(server.url || details.server_url || 'N/A')}</span></div>
                <div class="subscription-row"><span class="subscription-label">Server Port</span><span class="subscription-value">${escapeHtml(server.port || details.server_port || 'N/A')}</span></div>
                <div class="subscription-row"><span class="subscription-label">Server Protocol</span><span class="subscription-value">${escapeHtml(server.server_protocol || 'N/A')}</span></div>
                <div class="subscription-row"><span class="subscription-label">Server Timezone</span><span class="subscription-value">${escapeHtml(server.timezone || details.server_timezone || 'N/A')}</span></div>
                <div class="subscription-row"><span class="subscription-label">Server Time</span><span class="subscription-value">${escapeHtml(server.time_now || details.server_time_now || 'N/A')}</span></div>
            </div>
        </div>
    `;
}

// Data Fetching
async function loadCategories() {
    const url = document.getElementById('url').value.trim();
    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value.trim();
    const includeVod = document.getElementById('includeVod').checked;

    if (!state.activeProfileKey) {
        showError('Setup a server first.');
        return;
    }

    if (!url || !username || !password) {
        showError('Setup a server first.');
        return;
    }

    // Update state
    state.credentials = { url, username, password, includeVod };
    console.info('[loadCategories] starting', { url, username, includeVod });

    showLoading('Connecting to IPTV service...');
    document.getElementById('loadBtn').disabled = true;

    try {
        const params = new URLSearchParams({
            url, username, password,
            include_vod: includeVod
        });

        const categoriesResponse = await fetch(`/categories?${params}`);
        const data = await categoriesResponse.json();
        console.info('[loadCategories] categories response', {
            status: categoriesResponse.status,
            ok: categoriesResponse.ok,
            categoryCount: Array.isArray(data) ? data.length : (Array.isArray(data?.categories) ? data.categories.length : null),
            streamCount: Array.isArray(data?.streams) ? data.streams.length : null
        });

        if (!categoriesResponse.ok) {
            throw new Error(data.details || data.error || 'Failed to fetch categories');
        }

        try {
            const subscriptionResponse = await fetch(`/subscription?${params}`);
            if (subscriptionResponse.ok) {
                state.subscription = await subscriptionResponse.json();
            } else {
                state.subscription = null;
            }
        } catch (_subscriptionError) {
            state.subscription = null;
        }

        state.categories = Array.isArray(data) ? data : (Array.isArray(data.categories) ? data.categories : []);
        state.streams = Array.isArray(data?.streams) ? data.streams : [];
        state.selectedChannelIds = new Set();
        syncSelectedCategoriesFromChannels();
        state.searchTerm = '';
        state.collapsedSections = new Set(['live', 'vod', 'series']);
        elements.searchInput.value = '';
        renderCategories();
        renderSubscriptionDetails();
        showStep(2);

    } catch (error) {
        console.error('[loadCategories] failed', error);
        showError(error.message);
        showStep(1);
    } finally {
        hideLoading();
        document.getElementById('loadBtn').disabled = false;
    }
}

// Category Rendering
function renderCategories() {
    elements.categoryChips.innerHTML = '';
    syncSelectedCategoriesFromChannels();

    const groups = {
        live: [],
        vod: [],
        series: []
    };

    state.categories.forEach(cat => {
        const type = cat.content_type || 'live';
        if (groups[type]) groups[type].push(cat);
    });

    const sectionConfig = [
        { key: 'live', title: '📺 Live Channels' },
        { key: 'vod', title: '🎬 Movies' },
        { key: 'series', title: '🍿 TV Series' }
    ];

    sectionConfig.forEach(section => {
        const cats = groups[section.key];
        if (cats && cats.length > 0) {
            // Wrapper
            const wrapper = document.createElement('div');
            wrapper.className = 'category-group-wrapper';
            wrapper.dataset.section = section.key;

            // Header
            const header = document.createElement('div');
            header.className = 'category-section-header';
            if (state.collapsedSections.has(section.key)) {
                header.classList.add('collapsed');
            }
            header.dataset.section = section.key;

            // Header content
            header.innerHTML = `
                <h3>
                    <span class="chevron">▼</span>
                    ${section.title}
                    <span style="font-size:0.8em; opacity:0.7">(${cats.length})</span>
                </h3>
                <button class="btn-section-select-all" data-section="${section.key}">Select All</button>
            `;

            // Click handler for collapsing
            header.onclick = (e) => {
                // Prevent collapsing when clicking the select all button
                if (e.target.classList.contains('btn-section-select-all')) return;
                toggleSection(section.key, header);
            };

            wrapper.appendChild(header);

            // Grid
            const grid = document.createElement('div');
            grid.className = 'category-section';
            grid.dataset.section = section.key;
            if (state.collapsedSections.has(section.key)) {
                grid.classList.add('hidden');
            }

            cats.forEach(cat => {
                const chip = document.createElement('div');
                chip.className = 'category-chip';
                const totalChannels = getCategoryStreams(cat).length;
                const selectedChannels = getSelectedChannelCountForCategory(cat);
                if (selectedChannels > 0) {
                    chip.classList.add('selected');
                }
                chip.dataset.id = cat.category_id;
                chip.dataset.name = cat.category_name;
                chip.dataset.type = section.key;
                chip.title = cat.category_name;
                chip.innerHTML = `
                    <div class="category-chip-main">
                        <div class="category-chip-title">${escapeHtml(cat.category_name)}</div>
                        <div class="category-chip-meta">${selectedChannels}/${totalChannels} channels selected</div>
                    </div>
                    <button class="btn-text btn-edit-channels" type="button">Edit Channels</button>
                `;

                chip.onclick = (e) => {
                    if (e.target.closest('.btn-edit-channels')) {
                        e.stopPropagation();
                    }
                    openChannelEditorModal(cat);
                };
                grid.appendChild(chip);
            });

            wrapper.appendChild(grid);
            elements.categoryChips.appendChild(wrapper);
        }
    });

    setupSectionToggles();
    updateCounter();
}

function toggleCategory(chip) {
    // Category selection is now derived from channel selection.
    updateCounter();
}

function toggleSection(sectionKey, headerElement) {
    const grid = document.querySelector(`.category-section[data-section="${sectionKey}"]`);
    if (grid) {
        if (grid.classList.contains('hidden')) {
            grid.classList.remove('hidden');
            headerElement.classList.remove('collapsed');
            state.collapsedSections.delete(sectionKey);
        } else {
            grid.classList.add('hidden');
            headerElement.classList.add('collapsed');
            state.collapsedSections.add(sectionKey);
        }
    }
}

function setupSectionToggles() {
    document.querySelectorAll('.btn-section-select-all').forEach(btn => {
        btn.onclick = (e) => {
            e.stopPropagation(); // Prevent header collapse
            const section = e.target.dataset.section;
            // Get visible chips only if we want to respect search?
            // Usually "Select All" in a section implies all in that section,
            // but if search is active, maybe only visible ones.
            // Let's make it select all visible ones in that section.

            const chips = document.querySelectorAll(`.category-chip[data-type="${section}"]:not(.hidden)`);
            if (chips.length === 0) return;
            const visibleCategories = Array.from(chips)
                .map((chip) => state.categories.find((cat) =>
                    String(cat.category_id) === String(chip.dataset.id)
                    && String(cat.content_type || 'live') === String(chip.dataset.type || 'live')
                ))
                .filter(Boolean);
            const allSelected = visibleCategories.every((cat) => {
                const streams = getCategoryStreams(cat);
                return streams.length > 0 && streams.every((stream) => state.selectedChannelIds.has(normalizeStreamId(stream)));
            });

            visibleCategories.forEach((cat) => {
                const streams = getCategoryStreams(cat);
                streams.forEach((stream) => {
                    const id = normalizeStreamId(stream);
                    if (!id) return;
                    if (allSelected) {
                        state.selectedChannelIds.delete(id);
                    } else {
                        state.selectedChannelIds.add(id);
                    }
                });
            });
            renderCategories();
            updateCounter();
        };
    });
}

function clearSelection() {
    state.selectedChannelIds.clear();
    syncSelectedCategoriesFromChannels();
    renderCategories();
    updateCounter();
}

function selectAllVisible() {
    const chips = document.querySelectorAll('.category-chip:not(.hidden)');
    chips.forEach((chip) => {
        const category = state.categories.find((cat) =>
            String(cat.category_id) === String(chip.dataset.id)
            && String(cat.content_type || 'live') === String(chip.dataset.type || 'live')
        );
        if (!category) return;
        getCategoryStreams(category).forEach((stream) => {
            const id = normalizeStreamId(stream);
            if (id) state.selectedChannelIds.add(id);
        });
    });
    syncSelectedCategoriesFromChannels();
    renderCategories();
    updateCounter();
}

function updateCounter() {
    syncSelectedCategoriesFromChannels();
    const groupCount = state.selectedCategories.size;
    const channelCount = state.selectedChannelIds.size;
    const mode = document.querySelector('input[name="filterMode"]:checked').value;
    state.filterMode = mode;

    if (channelCount === 0) {
        elements.selectionText.textContent = 'Select channels in a group to include it in your playlist';
        elements.selectionCounter.classList.remove('has-selection');
    } else {
        const action = mode === 'include' ? 'included' : 'excluded';
        elements.selectionText.innerHTML = `<strong>${groupCount}</strong> groups and <strong>${channelCount}</strong> channels will be ${action}`;
        elements.selectionCounter.classList.add('has-selection');
    }
}

function filterCategories(searchTerm) {
    state.searchTerm = searchTerm.toLowerCase();
    const chips = document.querySelectorAll('.category-chip');

    chips.forEach(chip => {
        const name = chip.dataset.name.toLowerCase();
        if (name.includes(state.searchTerm)) {
            chip.classList.remove('hidden');
        } else {
            chip.classList.add('hidden');
        }
    });

    // Also hide empty sections?
    document.querySelectorAll('.category-group-wrapper').forEach(wrapper => {
        const sectionKey = wrapper.dataset.section;
        const visibleChips = wrapper.querySelectorAll('.category-chip:not(.hidden)');

        if (visibleChips.length === 0) {
            wrapper.style.display = 'none';
        } else {
            wrapper.style.display = 'block';

            // Restore grid display if not collapsed
            const grid = wrapper.querySelector('.category-section');
            if (grid && !state.collapsedSections.has(sectionKey)) {
                // Grid should be visible (css handles grid display usually, but let's ensure)
                // The grid class .hidden handles it. If it doesn't have .hidden, it shows.
                // But wait, if we previously set style.display = 'none' on the grid directly...
            }
        }
    });
}

function openChannelEditorModal(category) {
    if (!elements.channelEditorModal || !category) return;
    state.channelEditorCategory = category;
    state.channelSearchTerm = '';
    if (elements.channelSearchInput) {
        elements.channelSearchInput.value = '';
    }
    if (elements.channelEditorTitle) {
        elements.channelEditorTitle.textContent = `Edit Channels: ${category.category_name}`;
    }
    renderChannelEditorList();
    if (elements.channelList) {
        elements.channelList.scrollTop = 0;
    }
    elements.channelEditorModal.classList.add('active');
}

function closeChannelEditorModal() {
    if (!elements.channelEditorModal) return;
    elements.channelEditorModal.classList.remove('active');
    state.channelEditorCategory = null;
    renderCategories();
    updateCounter();
}

function renderChannelEditorList() {
    if (!elements.channelList || !state.channelEditorCategory) return;
    const channels = getCategoryStreams(state.channelEditorCategory)
        .filter((stream) => {
            if (!state.channelSearchTerm) return true;
            const name = String(stream?.name || '').toLowerCase();
            return name.includes(state.channelSearchTerm);
        });

    if (channels.length === 0) {
        elements.channelList.innerHTML = '<div class="saved-playlist-item">No channels found.</div>';
    } else {
        elements.channelList.innerHTML = channels.map((stream) => {
            const id = normalizeStreamId(stream);
            const checked = id && state.selectedChannelIds.has(id);
            const contentType = String(stream?.content_type || 'live');
            const extension = String(stream?.container_extension || (contentType === 'live' ? 'ts' : 'mp4'));
            const inputId = `channel-select-${id}`;
            return `
                <div class="channel-item ${checked ? 'selected' : ''}" data-id="${escapeHtml(id)}">
                    <label class="channel-item-main" for="${escapeHtml(inputId)}">
                        <input id="${escapeHtml(inputId)}" type="checkbox" ${checked ? 'checked' : ''} onchange="toggleChannelSelection('${escapeHtml(id)}')">
                        <span class="channel-item-name">${escapeHtml(stream?.name || `Channel ${id}`)}</span>
                    </label>
                    <div class="channel-item-actions">
                        <button class="btn-text" type="button" onclick="openChannelViewer('${escapeHtml(id)}','${escapeHtml(contentType)}','${escapeHtml(extension)}','${escapeHtml(stream?.name || '')}')">View</button>
                    </div>
                </div>
            `;
        }).join('');
    }

    updateChannelEditorCounter();
}

function toggleChannelSelection(id) {
    const streamId = String(id || '').trim();
    if (!streamId) return;
    if (state.selectedChannelIds.has(streamId)) {
        state.selectedChannelIds.delete(streamId);
    } else {
        state.selectedChannelIds.add(streamId);
    }
    syncSelectedCategoriesFromChannels();
    renderChannelEditorList();
}

function closeChannelViewerModal() {
    destroyChannelViewer();
    if (elements.channelViewerVideo) {
        saveViewerPrefs(elements.channelViewerVideo);
        elements.channelViewerVideo.pause();
        elements.channelViewerVideo.removeAttribute('src');
        elements.channelViewerVideo.load();
    }
    if (elements.channelViewerModal) {
        elements.channelViewerModal.classList.remove('active');
    }
}

function setChannelViewerStatus(text, isError = false) {
    if (!elements.channelViewerStatus) return;
    elements.channelViewerStatus.textContent = text || '';
    elements.channelViewerStatus.style.color = isError ? 'var(--accent-danger)' : 'var(--text-secondary)';
}

function syncChannelViewerControlState() {
    const video = elements.channelViewerVideo;
    if (!video) return;
    if (elements.channelViewerPlayBtn) {
        elements.channelViewerPlayBtn.textContent = video.paused ? 'Play' : 'Pause';
    }
    if (elements.channelViewerMuteBtn) {
        elements.channelViewerMuteBtn.textContent = video.muted ? 'Unmute' : 'Mute';
    }
    if (elements.channelViewerVolume) {
        elements.channelViewerVolume.value = String(video.volume ?? 1);
    }
}

function loadViewerPrefs() {
    let volume = 1;
    try {
        const rawVolume = sessionStorage.getItem(VIEWER_VOLUME_KEY);
        const parsedVolume = Number(rawVolume);
        if (Number.isFinite(parsedVolume) && parsedVolume >= 0 && parsedVolume <= 1) {
            volume = parsedVolume;
        }
    } catch (_e) {}
    return { volume };
}

function saveViewerPrefs(video) {
    if (!video) return;
    try {
        sessionStorage.setItem(VIEWER_VOLUME_KEY, String(video.volume ?? 1));
    } catch (_e) {}
}

function destroyChannelViewer() {
    if (channelViewerHls) {
        try {
            channelViewerHls.destroy();
        } catch (_e) {}
        channelViewerHls = null;
    }
}

function waitForVideoEvent(video, timeoutMs = 25000) {
    return new Promise((resolve) => {
        let done = false;
        const finish = (ok) => {
            if (done) return;
            done = true;
            video.removeEventListener('playing', onPlaying);
            video.removeEventListener('canplay', onCanPlay);
            video.removeEventListener('loadedmetadata', onLoadedMetadata);
            video.removeEventListener('error', onError);
            clearTimeout(timer);
            resolve(ok);
        };
        const onPlaying = () => finish(true);
        const onCanPlay = () => finish(true);
        const onLoadedMetadata = () => finish(true);
        const onError = () => finish(false);
        const timer = setTimeout(() => finish(false), timeoutMs);
        video.addEventListener('playing', onPlaying, { once: true });
        video.addEventListener('canplay', onCanPlay, { once: true });
        video.addEventListener('loadedmetadata', onLoadedMetadata, { once: true });
        video.addEventListener('error', onError, { once: true });
    });
}

async function tryPlayChannelViewerStream(streamUrl, extension) {
    const video = elements.channelViewerVideo;
    if (!video || !streamUrl) return false;

    destroyChannelViewer();
    video.pause();
    const prefs = loadViewerPrefs();
    video.volume = prefs.volume;
    video.muted = true; // temporary mute for autoplay reliability
    video.removeAttribute('src');
    video.load();

    const isHls = String(extension || '').toLowerCase() === 'm3u8' || streamUrl.includes('.m3u8');

    if (isHls && window.Hls && window.Hls.isSupported()) {
        const hlsOk = await new Promise((resolve) => {
            let resolved = false;
            const finish = (ok) => {
                if (resolved) return;
                resolved = true;
                resolve(ok);
            };
            channelViewerHls = new window.Hls({
                enableWorker: true,
                lowLatencyMode: false,
                backBufferLength: 30
            });
            channelViewerHls.loadSource(streamUrl);
            channelViewerHls.attachMedia(video);
            channelViewerHls.on(window.Hls.Events.MANIFEST_PARSED, () => {
                video.play().catch(() => {});
            });
            channelViewerHls.on(window.Hls.Events.ERROR, (_event, data) => {
                if (data?.fatal) {
                    finish(false);
                }
            });
            waitForVideoEvent(video, 25000).then((ok) => finish(ok));
        });
        if (hlsOk) {
            return true;
        }
    }

    video.src = streamUrl;
    video.load();
    video.play().catch(() => {});
    return await waitForVideoEvent(video, 25000);
}

function buildStreamUrlCandidates(streamUrl) {
    const candidates = [];
    const base = String(streamUrl || '').trim();
    if (!base) return candidates;
    candidates.push(base);
    try {
        const parsed = new URL(base);
        const port = parsed.port || (parsed.protocol === 'https:' ? '443' : '80');
        if (parsed.protocol === 'https:' && port === '80') {
            const alt = new URL(base);
            alt.protocol = 'http:';
            candidates.push(alt.toString());
        }
        if (parsed.protocol === 'http:' && port === '443') {
            const alt = new URL(base);
            alt.protocol = 'https:';
            candidates.push(alt.toString());
        }
    } catch (_e) {
        // keep only original candidate
    }
    return Array.from(new Set(candidates));
}

function toggleChannelViewerPlayPause() {
    const video = elements.channelViewerVideo;
    if (!video) return;
    if (video.paused) {
        video.play().catch(() => {});
    } else {
        video.pause();
    }
}

function toggleChannelViewerMute() {
    const video = elements.channelViewerVideo;
    if (!video) return;
    video.muted = !video.muted;
    saveViewerPrefs(video);
    syncChannelViewerControlState();
}

function toggleChannelViewerFullscreen() {
    const video = elements.channelViewerVideo;
    if (!video) return;
    if (document.fullscreenElement) {
        document.exitFullscreen().catch(() => {});
        return;
    }
    video.requestFullscreen?.().catch(() => {});
}

async function openChannelViewer(streamId, contentType = 'live', extension = 'ts', streamName = '') {
    const id = String(streamId || '').trim();
    if (!id) return;
    const url = document.getElementById('url').value.trim();
    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value.trim();
    if (!url || !username || !password) {
        showError('Missing service credentials for stream viewer.');
        return;
    }

    try {
        if (elements.channelViewerTitle) {
            elements.channelViewerTitle.textContent = streamName ? `Channel Viewer: ${streamName}` : 'Channel Viewer';
        }
        if (elements.channelViewerModal) {
            elements.channelViewerModal.classList.add('active');
        }
        const video = elements.channelViewerVideo;
        if (!video) return;

        const isLive = String(contentType || 'live') === 'live';
        const extensions = isLive ? ['m3u8', 'ts'] : [extension || 'mp4'];
        const attempted = [];
        let started = false;

        for (const ext of Array.from(new Set(extensions.filter(Boolean)))) {
            attempted.push(ext);
            setChannelViewerStatus(`Loading ${ext.toUpperCase()}...`);
            const params = new URLSearchParams({
                url,
                username,
                password,
                stream_id: id,
                content_type: contentType || 'live',
                extension: ext
            });
            const response = await fetch(`/stream-link?${params.toString()}`);
            const data = await response.json();
            if (!response.ok) {
                continue;
            }
            const streamUrl = String(data.url || '').trim();
            if (!streamUrl) {
                continue;
            }
            const streamCandidates = buildStreamUrlCandidates(streamUrl);
            for (const candidate of streamCandidates) {
                const ok = await tryPlayChannelViewerStream(candidate, ext);
                if (ok) {
                    started = true;
                    break;
                }
            }
            if (started) {
                break;
            }
        }

        if (!started) {
            throw new Error(`Unable to play stream with: ${attempted.join(', ')}`);
        }

        if (elements.channelViewerVideo) {
            const prefs = loadViewerPrefs();
            elements.channelViewerVideo.volume = prefs.volume;
            elements.channelViewerVideo.muted = prefs.volume <= 0;
            saveViewerPrefs(elements.channelViewerVideo);
        }
        setChannelViewerStatus('Ready');
        syncChannelViewerControlState();
    } catch (error) {
        console.error('[openChannelViewer] failed', error);
        setChannelViewerStatus('Failed to load stream', true);
        showError(error.message);
    }
}

function updateChannelEditorCounter() {
    if (!elements.channelSelectionText || !state.channelEditorCategory) return;
    const channels = getCategoryStreams(state.channelEditorCategory);
    const selectedCount = channels.reduce((acc, stream) => acc + (state.selectedChannelIds.has(normalizeStreamId(stream)) ? 1 : 0), 0);
    elements.channelSelectionText.innerHTML = `<strong>${selectedCount}</strong> of <strong>${channels.length}</strong> channels selected`;
    if (elements.channelSelectionCounter) {
        if (selectedCount > 0) {
            elements.channelSelectionCounter.classList.add('has-selection');
        } else {
            elements.channelSelectionCounter.classList.remove('has-selection');
        }
    }
}

function selectAllVisibleChannels() {
    if (!state.channelEditorCategory) return;
    const channels = getCategoryStreams(state.channelEditorCategory)
        .filter((stream) => {
            if (!state.channelSearchTerm) return true;
            const name = String(stream?.name || '').toLowerCase();
            return name.includes(state.channelSearchTerm);
        });
    channels.forEach((stream) => {
        const id = normalizeStreamId(stream);
        if (id) state.selectedChannelIds.add(id);
    });
    syncSelectedCategoriesFromChannels();
    renderChannelEditorList();
}

function clearChannelSelection() {
    if (!state.channelEditorCategory) return;
    getCategoryStreams(state.channelEditorCategory).forEach((stream) => {
        const id = normalizeStreamId(stream);
        if (id) state.selectedChannelIds.delete(id);
    });
    syncSelectedCategoriesFromChannels();
    renderChannelEditorList();
}

// API Builder
function showApiBuilder() {
    elements.apiBuilderModal.classList.add('active');
    updateApiUrl();
}

function closeApiBuilder() {
    elements.apiBuilderModal.classList.remove('active');
}

function openPlaylistBuilderModal(createMode = true) {
    if (!elements.playlistBuilderModal) return;
    if (createMode) {
        state.playlistModalMode = 'create';
        state.editingPlaylistId = null;
        state.editingPlaylistOwner = '';
        state.selectedCategories = new Set();
        state.selectedChannelIds = new Set();
        state.filterMode = 'include';
        state.searchTerm = '';
        if (elements.playlistBuilderName) elements.playlistBuilderName.value = '';
        if (elements.searchInput) elements.searchInput.value = '';
        if (elements.playlistBuilderTitle) elements.playlistBuilderTitle.textContent = 'Create Playlist';
        if (elements.playlistBuilderSaveBtn) elements.playlistBuilderSaveBtn.textContent = 'Save Playlist';
    } else {
        if (elements.playlistBuilderTitle) elements.playlistBuilderTitle.textContent = 'Edit Playlist';
        if (elements.playlistBuilderSaveBtn) elements.playlistBuilderSaveBtn.textContent = 'Update Playlist';
    }
    syncFilterModeControls();
    renderCategories();
    updateCounter();
    elements.playlistBuilderModal.classList.add('active');
}

function closePlaylistBuilderModal() {
    if (!elements.playlistBuilderModal) return;
    elements.playlistBuilderModal.classList.remove('active');
}

function syncFilterModeControls() {
    document.querySelectorAll('input[name="filterMode"]').forEach((radio) => {
        radio.checked = radio.value === state.filterMode;
    });
}

function updateApiUrl() {
    const apiType = document.getElementById('apiType').value;
    const noStreamProxy = document.getElementById('apiNoStreamProxy').checked;
    const includeChannelId = document.getElementById('apiIncludeChannelId').checked;
    const proxyUrl = document.getElementById('apiProxyUrl').value.trim();
    const channelIdTag = document.getElementById('apiChannelIdTag').value.trim();

    // Toggle options visibility
    const m3uOptions = document.getElementById('m3uOptions');
    const advancedApiOptions = document.getElementById('advancedApiOptions');
    if (apiType === 'm3u') {
        m3uOptions.style.display = 'block';
    } else {
        m3uOptions.style.display = 'none';
    }
    advancedApiOptions.style.display = 'none';

    const baseUrl = window.location.origin;
    const params = new URLSearchParams({
        url: state.credentials.url,
        username: state.credentials.username,
        password: state.credentials.password
    });

    if (state.credentials.includeVod) {
        // Backend expects 'include_vod'
        params.append('include_vod', 'true');
    }

    // Smart filtering: Omit filter params if they result in "All Content"
    const categories = Array.from(state.selectedCategories);
    const channelIds = Array.from(state.selectedChannelIds);
    const totalCategories = state.categories.length;

    // Logic for omitting params:
    // If Filter Mode is INCLUDE:
    //   - If ALL categories are selected -> Omit (Implicitly Include All)
    //   - If SOME categories are selected -> Include 'wanted_groups'
    //   - If NO categories are selected -> (Technically this would result in empty playlist, but usually implies 'Select something'.
    //     However, if we want to follow strict logic: Include 'wanted_groups=' (empty) or just don't append.
    //     Let's assume user wants *something*. If 0 selected in include mode, the URL will produce nothing anyway.

    // If Filter Mode is EXCLUDE:
    //   - If NO categories are selected -> Omit (Implicitly Exclude None = Include All)
    //   - If SOME categories are selected -> Include 'unwanted_groups'

    if (categories.length > 0 && channelIds.length === 0) {
        if (state.filterMode === 'include') {
            // Only append if NOT all are selected
            if (categories.length < totalCategories) {
                params.append('wanted_groups', categories.join(','));
            }
        } else {
            // Exclude mode: Append unwanted groups
            params.append('unwanted_groups', categories.join(','));
        }
    } else {
        // Categories length is 0
        if (state.filterMode === 'include') {
            // Include mode + 0 selected = Empty playlist?
            // Or does user imply "All"? Usually UI starts empty.
            // If we omit, it defaults to ALL.
            // If user explicitly selected NOTHING in "Include Mode", they probably don't want ALL.
            // But for the API URL builder, let's assume if they selected nothing, they haven't configured filters, so defaulting to ALL (omitting) might be safer or adding an empty param.
            // But let's stick to the prompt: "we should not need to actually include all the categories, we should be able to just ommit it"
            // This implies the user selected ALL.

            // So if count == 0 in include mode, maybe they haven't started.
            // But if they selected ALL (via Select All), count == total.
            // The check `categories.length < totalCategories` above handles the "Selected All" case for Include mode.
        }
    }

    if (channelIds.length > 0) {
        if (state.filterMode === 'include') {
            params.append('wanted_stream_ids', channelIds.join(','));
        } else {
            params.append('unwanted_stream_ids', channelIds.join(','));
        }
    }

    if (apiType === 'm3u') {
        if (noStreamProxy) params.append('nostreamproxy', 'true');
        if (includeChannelId) params.append('include_channel_id', 'true');
        if (proxyUrl) params.append('proxy_url', proxyUrl);
        if (channelIdTag) params.append('channel_id_tag', channelIdTag);

        elements.generatedApiUrl.textContent = `${baseUrl}/m3u?${params.toString()}`;
        return;
    }

    if (apiType === 'xmltv') {
        if (proxyUrl) params.append('proxy_url', proxyUrl);
        elements.generatedApiUrl.textContent = `${baseUrl}/xmltv?${params.toString()}`;
        return;
    }

    if (apiType === 'categories') {
        elements.generatedApiUrl.textContent = `${baseUrl}/categories?${params.toString()}`;
        return;
    }
}

function copyApiUrl(buttonEl) {
    const url = (elements.generatedApiUrl?.textContent || '').trim();
    if (!url) {
        showError('No generated URL to copy.');
        return;
    }
    copyTextToClipboard(url).then(() => {
        const btn = buttonEl;
        if (!btn) return;
        const originalText = btn.textContent;
        btn.textContent = '✅';
        setTimeout(() => { btn.textContent = originalText; }, 1500);
    }).catch((error) => {
        console.error('[copyApiUrl] failed', error);
        showError('Could not copy URL. Please copy manually.');
    });
}

function buildPlaylistRequestDataFromState() {
    const activeProfile = getActiveProfile();
    const owner = state.playlistModalMode === 'edit'
        ? String(state.editingPlaylistOwner || activeProfile?.owner || '').trim()
        : String(activeProfile?.owner || '').trim();

    const requestData = {
        ...state.credentials,
        nostreamproxy: true,
        include_vod: state.credentials.includeVod,
        owner
    };
    delete requestData.includeVod;

    const channelIds = Array.from(state.selectedChannelIds);
    const categories = Array.from(state.selectedCategories);
    if (categories.length > 0 && channelIds.length === 0) {
        if (state.filterMode === 'include') {
            requestData.wanted_groups = categories.join(',');
        } else {
            requestData.unwanted_groups = categories.join(',');
        }
    }
    if (channelIds.length > 0) {
        if (state.filterMode === 'include') {
            requestData.wanted_stream_ids = channelIds.join(',');
        } else {
            requestData.unwanted_stream_ids = channelIds.join(',');
        }
    }
    return requestData;
}

function copySavedPlaylistUrl(targetId, buttonEl) {
    const target = document.getElementById(targetId);
    if (!target || !target.textContent) return;
    copyTextToClipboard(target.textContent).then(() => {
        const btn = buttonEl;
        if (!btn) return;
        const originalText = btn.textContent;
        btn.textContent = '✅';
        setTimeout(() => { btn.textContent = originalText; }, 1500);
    }).catch((error) => {
        console.error('[copySavedPlaylistUrl] failed', error);
        showError('Could not copy URL. Please copy manually.');
    });
}

async function savePlaylistFromModal() {
    const playlistName = (elements.modalPlaylistName?.value || '').trim();
    if (!playlistName) {
        openWarningModal('Playlist name is required.');
        return;
    }

    const payload = {
        ...buildPlaylistRequestDataFromState(),
        name: playlistName
    };
    if (state.playlistModalMode === 'edit' && state.editingPlaylistId) {
        payload.id = state.editingPlaylistId;
    }

    try {
        const response = await fetch('/saved-playlists', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.details || data.error || 'Failed to save playlist');
        }
        state.playlistModalMode = 'edit';
        state.editingPlaylistId = data.id || state.editingPlaylistId;
        await loadSavedPlaylistsList();
        closeModal();
    } catch (error) {
        console.error('[savePlaylistFromModal] failed', error);
        showError(error.message);
    }
}

async function savePlaylistFromBuilderModal() {
    const playlistName = (elements.playlistBuilderName?.value || '').trim();
    if (!playlistName) {
        openWarningModal('Playlist name is required.');
        return;
    }

    const payload = {
        ...buildPlaylistRequestDataFromState(),
        name: playlistName
    };
    if (state.playlistModalMode === 'edit' && state.editingPlaylistId) {
        payload.id = state.editingPlaylistId;
    }

    try {
        const response = await fetch('/saved-playlists', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.details || data.error || 'Failed to save playlist');
        }
        state.playlistModalMode = 'edit';
        state.editingPlaylistId = data.id || state.editingPlaylistId;
        state.editingPlaylistOwner = data.owner || state.editingPlaylistOwner;
        await loadSavedPlaylistsList();
        closePlaylistBuilderModal();
    } catch (error) {
        console.error('[savePlaylistFromBuilderModal] failed', error);
        showError(error.message);
    }
}

async function loadSavedPlaylistsList() {
    if (!elements.savedPlaylistsList) return;
    try {
        const serviceUrl = document.getElementById('url').value.trim();
        const serviceUsername = document.getElementById('username').value.trim();
        const params = new URLSearchParams({
            url: serviceUrl,
            username: serviceUsername
        });
        const response = await fetch(`/saved-playlists?${params.toString()}`);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.details || data.error || 'Failed to load saved playlists');
        }
        const items = Array.isArray(data.items) ? data.items : [];
        if (items.length === 0) {
            elements.savedPlaylistsList.innerHTML = '<div class="saved-playlist-item">No saved playlists yet.</div>';
            return;
        }
        elements.savedPlaylistsList.innerHTML = items
            .map(item => `
                <div class="saved-playlist-item">
                    <div class="saved-playlist-main">
                        <strong>${escapeHtml(item.name || item.id)}</strong>
                        <small>Owner: ${escapeHtml(item.owner || 'N/A')}</small>
                        <small>M3U: ${escapeHtml(item.m3u_url || item.url || '')}</small>
                        <small>EPG: ${escapeHtml(item.xmltv_url || '')}</small>
                    </div>
                    <div style="display:flex; gap:0.35rem;">
                        <button class="btn-copy" type="button" title="Edit Playlist" onclick="editSavedPlaylist('${escapeHtml(item.id || '')}')">✏️</button>
                        <button class="btn-copy" type="button" title="Copy M3U URL" data-url="${encodeURIComponent(item.m3u_url || item.url || '')}" onclick="copySavedPlaylistListUrl(this)">📋</button>
                        <button class="btn-copy" type="button" title="View M3U Content" onclick="openSavedPlaylistDebug('${escapeHtml(item.id || '')}','m3u')">🧪</button>
                        <button class="btn-copy" type="button" title="Copy XMLTV URL" data-url="${encodeURIComponent(item.xmltv_url || '')}" onclick="copySavedPlaylistListUrl(this)">📰</button>
                        <button class="btn-copy" type="button" title="View XMLTV Content" onclick="openSavedPlaylistDebug('${escapeHtml(item.id || '')}','xmltv')">🔎</button>
                        <button class="btn-copy" type="button" title="Delete Saved Playlist" onclick="deleteSavedPlaylist('${escapeHtml(item.id || '')}')">🗑️</button>
                    </div>
                </div>
            `)
            .join('');
    } catch (error) {
        console.error('[loadSavedPlaylistsList] failed', error);
        elements.savedPlaylistsList.innerHTML = '<div class="saved-playlist-item">Failed to load saved playlists.</div>';
    }
}

async function editSavedPlaylist(id) {
    if (!id) return;
    try {
        const response = await fetch(`/saved-playlists/${encodeURIComponent(id)}`);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.details || data.error || 'Failed to load saved playlist');
        }
        const config = data.config || {};

        state.playlistModalMode = 'edit';
        state.editingPlaylistId = data.id;
        state.editingPlaylistOwner = String(data.owner || '').trim();
        if (elements.playlistBuilderName) elements.playlistBuilderName.value = data.name || '';

        state.filterMode = (config.wanted_groups || config.wanted_stream_ids) ? 'include' : 'exclude';
        if (config.wanted_groups) {
            state.selectedCategories = new Set(parseCsv(config.wanted_groups));
        } else if (config.unwanted_groups) {
            state.selectedCategories = new Set(parseCsv(config.unwanted_groups));
        } else {
            state.selectedCategories = new Set();
        }
        if (config.wanted_stream_ids) {
            state.selectedChannelIds = new Set(parseCsv(config.wanted_stream_ids));
        } else if (config.unwanted_stream_ids) {
            state.selectedChannelIds = new Set(parseCsv(config.unwanted_stream_ids));
        } else {
            state.selectedChannelIds = new Set();
        }
        if (state.selectedChannelIds.size === 0 && state.selectedCategories.size > 0) {
            state.categories.forEach((category) => {
                if (!state.selectedCategories.has(String(category.category_name || '').trim())) return;
                getCategoryStreams(category).forEach((stream) => {
                    const id = normalizeStreamId(stream);
                    if (id) state.selectedChannelIds.add(id);
                });
            });
        }
        syncSelectedCategoriesFromChannels();
        state.credentials.includeVod = String(config.include_vod).toLowerCase() === 'true';
        document.getElementById('includeVod').checked = state.credentials.includeVod;
        openPlaylistBuilderModal(false);
    } catch (error) {
        console.error('[editSavedPlaylist] failed', error);
        showError(error.message);
    }
}

function parseCsv(text) {
    if (!text) return [];
    return String(text).split(',').map(v => v.trim()).filter(Boolean);
}

async function deleteSavedPlaylist(id) {
    if (!id) return;
    state.pendingDelete = { type: 'saved_playlist', id };
    openDeleteConfirmModal('Delete this saved playlist?');
}

async function executeDeleteSavedPlaylist(id) {
    if (!id) return;
    try {
        const response = await fetch('/saved-playlists/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id })
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.details || data.error || 'Failed to delete saved playlist');
        }
        await loadSavedPlaylistsList();
    } catch (error) {
        console.error('[deleteSavedPlaylist] failed', error);
        showError(error.message);
    }
}

function openDeleteConfirmModal(message) {
    if (!elements.deleteConfirmModal) return;
    if (elements.deleteConfirmText) {
        elements.deleteConfirmText.textContent = message || 'Are you sure you want to delete this item?';
    }
    elements.deleteConfirmModal.classList.add('active');
}

function closeDeleteConfirmModal() {
    if (elements.deleteConfirmModal) {
        elements.deleteConfirmModal.classList.remove('active');
    }
    state.pendingDelete = null;
}

function openWarningModal(message) {
    if (!elements.warningModal) {
        showError(message || 'Please review required fields.');
        return;
    }
    if (elements.warningModalText) {
        elements.warningModalText.textContent = message || 'Please review required fields.';
    }
    elements.warningModal.classList.add('active');
}

function closeWarningModal() {
    if (elements.warningModal) {
        elements.warningModal.classList.remove('active');
    }
}

async function confirmDeleteAction() {
    const pending = state.pendingDelete;
    if (!pending) {
        closeDeleteConfirmModal();
        return;
    }
    closeDeleteConfirmModal();
    if (pending.type === 'profile') {
        await executeDeleteCurrentProfile(pending.id);
        return;
    }
    if (pending.type === 'saved_playlist') {
        await executeDeleteSavedPlaylist(pending.id);
        return;
    }
    if (pending.type === 'auth_user') {
        await executeDeleteAuthUser(pending.id);
    }
}

function copySavedPlaylistListUrl(button) {
    const encoded = button?.dataset?.url || '';
    const decoded = decodeURIComponent(encoded);
    if (!decoded) return;
    copyTextToClipboard(decoded).then(() => {
        const originalText = button.textContent;
        button.textContent = '✅';
        setTimeout(() => { button.textContent = originalText; }, 1500);
    }).catch((error) => {
        console.error('[copySavedPlaylistListUrl] failed', error);
        showError('Could not copy URL. Please copy manually.');
    });
}

function openSavedPlaylistDebug(id, kind) {
    const playlistId = String(id || '').trim();
    const type = String(kind || '').trim().toLowerCase();
    if (!playlistId || !['m3u', 'xmltv'].includes(type)) return;
    const url = `/playlist/${encodeURIComponent(playlistId)}/${type}?preview=true`;
    window.open(url, '_blank', 'noopener');
}

async function copyTextToClipboard(text) {
    if (!text) throw new Error('No text to copy');
    if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return;
    }

    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.setAttribute('readonly', '');
    textArea.style.position = 'fixed';
    textArea.style.left = '-9999px';
    document.body.appendChild(textArea);
    textArea.select();
    textArea.setSelectionRange(0, textArea.value.length);
    const ok = document.execCommand('copy');
    document.body.removeChild(textArea);
    if (!ok) {
        throw new Error('execCommand copy failed');
    }
}

// Confirmation & Generation
function showConfirmation(createMode = true) {
    const count = state.selectedCategories.size;
    closePlaylistBuilderModal();
    elements.confirmationModal.classList.add('active');
    if (createMode) {
        state.playlistModalMode = 'create';
        state.editingPlaylistId = null;
        if (elements.modalPlaylistName) elements.modalPlaylistName.value = '';
    }
    if (elements.modalSavedLinks) elements.modalSavedLinks.style.display = 'none';
    if (elements.modalSavedM3uUrl) elements.modalSavedM3uUrl.textContent = '';
    if (elements.modalSavedXmltvUrl) elements.modalSavedXmltvUrl.textContent = '';

    // Check filter mode again just in case
    state.filterMode = document.querySelector('input[name="filterMode"]:checked').value;
    const action = state.filterMode === 'include' ? 'Include' : 'Exclude';
    const desc = count === 0 ? 'All Categories' : `${action} ${count} categories`;

    // Check for TV Series selection
    let seriesWarning = '';
    const hasSeriesSelected = Array.from(state.selectedCategories).some(name => {
        // Find category object to check type
        const cat = state.categories.find(c => c.category_name === name);
        return cat && cat.content_type === 'series';
    });

    if (state.credentials.includeVod && (state.filterMode === 'include' && hasSeriesSelected)) {
         seriesWarning = `
            <div class="alert alert-warning" style="margin-top: 1rem; font-size: 0.85rem; align-items: flex-start;">
                <span style="font-size: 1.2rem; line-height: 1;">⚠️</span>
                <div>
                    <strong>TV Series Selected</strong><br>
                    Fetching episode data is limited by the Xtream API speed.<br>
                    <span style="opacity: 0.9">Processing may take a significant amount of time (minutes to hours) depending on the number of series.</span>
                </div>
            </div>
        `;
    }

    const subscriptionRows = state.subscription ? `
        <div class="summary-row">
            <span class="summary-label">Subscription Status</span>
            <span class="summary-value">${escapeHtml(state.subscription.status || 'Unknown')}</span>
        </div>
        <div class="summary-row">
            <span class="summary-label">Expiry</span>
            <span class="summary-value">${escapeHtml(formatUnixTimestamp(state.subscription.exp_date))}</span>
        </div>
        <div class="summary-row">
            <span class="summary-label">Connections</span>
            <span class="summary-value">${escapeHtml(state.subscription.active_cons || '0')} / ${escapeHtml(state.subscription.max_connections || '0')}</span>
        </div>
    ` : '';

    elements.modalSummary.innerHTML = `
        <div class="summary-row">
            <span class="summary-label">Service URL</span>
            <span class="summary-value" style="max-width: 200px; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(state.credentials.url)}</span>
        </div>
        <div class="summary-row">
            <span class="summary-label">Content</span>
            <span class="summary-value">${state.credentials.includeVod ? 'Live TV + VOD' : 'Live TV Only'}</span>
        </div>
        <div class="summary-row">
            <span class="summary-label">Filter Config</span>
            <span class="summary-value">${desc}</span>
        </div>
        ${subscriptionRows}
        ${seriesWarning}
    `;
}

function closeModal() {
    elements.confirmationModal.classList.remove('active');
}

async function confirmGeneration() {
    closeModal();
    showLoading('Generating Playlist...');

    const requestData = buildPlaylistRequestDataFromState();
    const categories = Array.from(state.selectedCategories);

    try {
        // Decide method based on payload size
        const usePost = categories.length > 10 || JSON.stringify(requestData).length > 1500;

        let response;
        if (usePost) {
            response = await fetch('/m3u', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData)
            });
        } else {
            const params = new URLSearchParams(requestData);
            response = await fetch(`/m3u?${params}`);
        }

        if (!response.ok) throw new Error('Generation failed');

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);

        elements.downloadLink.href = url;
        elements.downloadLink.download = state.credentials.includeVod ? 'Full_Playlist.m3u' : 'Live_Playlist.m3u';
        state.lastGeneratedConfig = requestData;
        await loadSavedPlaylistsList();
        showStep(3);

    } catch (error) {
        console.error(error);
        showError('Failed to generate playlist. Please check your inputs and try again.');
        showStep(2);
    } finally {
        hideLoading();
    }
}

function startOver() {
    if (elements.modalSavedLinks) elements.modalSavedLinks.style.display = 'none';
    if (elements.modalSavedM3uUrl) elements.modalSavedM3uUrl.textContent = '';
    if (elements.modalSavedXmltvUrl) elements.modalSavedXmltvUrl.textContent = '';
    if (elements.modalPlaylistName) elements.modalPlaylistName.value = '';
    state.lastGeneratedConfig = null;

    if (state.categories && state.categories.length > 0) {
        showStep(2);
    } else {
        applyActiveProfileToForm();
        state.selectedCategories.clear();
        state.selectedChannelIds.clear();
        state.searchTerm = '';
        state.subscription = null;
        elements.searchInput.value = '';
        renderSubscriptionDetails();
        showStep(1);
    }
}

// Event Listeners
document.addEventListener('DOMContentLoaded', async () => {
    const setupUsernameEl = document.getElementById('setupUsername');
    const setupPasswordEl = document.getElementById('setupPassword');
    const loginUsernameEl = document.getElementById('loginUsername');
    const loginPasswordEl = document.getElementById('loginPassword');

    [setupUsernameEl, setupPasswordEl].forEach((el) => {
        if (!el) return;
        el.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                submitAuthSetup();
            }
        });
    });

    [loginUsernameEl, loginPasswordEl].forEach((el) => {
        if (!el) return;
        el.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                submitAuthLogin();
            }
        });
    });

    if (elements.profileSelect) {
        elements.profileSelect.addEventListener('change', (e) => onProfileChanged(e.target.value));
    }

    // Filter mode change
    document.querySelectorAll('input[name="filterMode"]').forEach(radio => {
        radio.addEventListener('change', updateCounter);
    });

    // Search input
    elements.searchInput.addEventListener('input', (e) => {
        filterCategories(e.target.value);
    });
    if (elements.channelSearchInput) {
        elements.channelSearchInput.addEventListener('input', (e) => {
            state.channelSearchTerm = String(e.target.value || '').toLowerCase();
            renderChannelEditorList();
        });
    }

    // Close modal on outside click
    elements.confirmationModal.addEventListener('click', (e) => {
        if (e.target === elements.confirmationModal) closeModal();
    });

    if (elements.newProfileModal) {
        elements.newProfileModal.addEventListener('click', (e) => {
            if (e.target === elements.newProfileModal) closeNewProfileModal();
        });
    }

    if (elements.playlistBuilderModal) {
        // Intentionally no outside-click close: modal closes via explicit buttons only.
    }
    if (elements.channelEditorModal) {
        // Intentionally no outside-click close: modal closes only via "Done".
    }
    if (elements.channelViewerModal) {
        elements.channelViewerModal.addEventListener('click', (e) => {
            if (e.target === elements.channelViewerModal) closeChannelViewerModal();
        });
    }
    if (elements.channelViewerVideo) {
        elements.channelViewerVideo.addEventListener('play', () => {
            setChannelViewerStatus('Playing');
            syncChannelViewerControlState();
        });
        elements.channelViewerVideo.addEventListener('pause', () => {
            const video = elements.channelViewerVideo;
            if (!video) return;
            if (video.ended) {
                setChannelViewerStatus('Ended');
            } else if (video.readyState < 2) {
                setChannelViewerStatus('Buffering...');
            } else {
                setChannelViewerStatus('Paused');
            }
            syncChannelViewerControlState();
        });
        elements.channelViewerVideo.addEventListener('ended', () => {
            setChannelViewerStatus('Ended');
            syncChannelViewerControlState();
        });
        elements.channelViewerVideo.addEventListener('error', () => {
            setChannelViewerStatus('Playback error', true);
        });
    }
    if (elements.channelViewerVolume) {
        elements.channelViewerVolume.addEventListener('input', (e) => {
            const video = elements.channelViewerVideo;
            if (!video) return;
            const value = Number(e.target.value);
            video.volume = Number.isFinite(value) ? value : 1;
            if (video.volume > 0 && video.muted) {
                video.muted = false;
            }
            saveViewerPrefs(video);
            syncChannelViewerControlState();
        });
    }

    if (elements.deleteConfirmModal) {
        elements.deleteConfirmModal.addEventListener('click', (e) => {
            if (e.target === elements.deleteConfirmModal) closeDeleteConfirmModal();
        });
    }

    if (elements.addUserModal) {
        elements.addUserModal.addEventListener('click', (e) => {
            if (e.target === elements.addUserModal) closeAddUserModal();
        });
    }

    if (elements.backupModal) {
        elements.backupModal.addEventListener('click', (e) => {
            if (e.target === elements.backupModal) closeBackupModal();
        });
    }

    // Input trim handlers
    document.querySelectorAll('input').forEach(input => {
        input.addEventListener('blur', (e) => {
            if(e.target.type !== 'checkbox' && e.target.type !== 'radio') {
                e.target.value = e.target.value.trim();
            }
        });
    });

    try {
        const status = await getAuthStatus();
        state.authenticated = Boolean(status.authenticated);
        state.currentUsername = String(status.username || '').trim();
        state.isAdmin = Boolean(status.is_admin);
        renderAuthControls();
        if (status.needs_setup) {
            state.appInitialized = false;
            showAuthModal({ needsSetup: true });
            updateConnectionAvailability();
            return;
        }
        if (!status.authenticated) {
            state.appInitialized = false;
            showAuthModal({ needsSetup: false });
            updateConnectionAvailability();
            return;
        }
        hideAuthModal();
        await initializeApp();
    } catch (error) {
        console.error('[auth init] failed', error);
        showError('Authentication check failed.');
        showAuthModal({ needsSetup: false });
        updateConnectionAvailability();
        renderAuthControls();
    }
});
