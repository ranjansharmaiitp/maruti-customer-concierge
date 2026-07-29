/**
 * Car AI Doctor — Real-Time Voice Assistant Engine
 * Inspired by Sarvam Voice live conversational interface:
 * - Primed AudioContext & audio element on user click (100% reliable out-loud TTS playback).
 * - Continuous duplex mic stream with Voice Activity Detection (VAD).
 * - Instant Barge-In (speech interrupt support).
 * - Sarvam AI Automotive Diagnostic pipeline (Urgency rating, Checklist, Expert Call booking).
 */

document.addEventListener('DOMContentLoaded', () => {

    // ── State ──
    let sessionId = localStorage.getItem('car_ai_session_id') || 'session_' + Math.random().toString(36).substr(2, 9);
    localStorage.setItem('car_ai_session_id', sessionId);

    let phase = 'idle'; // 'idle', 'connecting', 'listening', 'hearing', 'thinking', 'speaking'
    let isRunning = false;
    let selectedLanguage = 'hi-IN';
    let selectedSpeaker = 'ShubhMale';
    let turnCount = 0;
    let lastSummary = '';
    let assistantMode = localStorage.getItem('car_ai_assistant_mode') || 'DIAGNOSTIC';
    let testDriveWelcomed = false;
    let testDriveStep = 1;
    let testDriveDealers = [];
    let testDriveCars = [];

    // Audio & VAD Engine
    let audioCtx = null;
    let analyserNode = null;
    let micStream = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let vadCheckInterval = null;
    let speechDetected = false;
    let silenceStartTimestamp = null;
    let visualizerAnimationId = null;
    let maxRecordingTimeout = null;
    let currentAudioSource = null;
    let playbackToken = 0;
    let bargeInSpeechStart = null;
    let bargeInArmTimeout = null;
    let vadNoiseFloor = 2;
    let vadSpeechFrames = 0;
    let lastSpeechTimestamp = null;

    const SILENCE_DURATION_THRESHOLD = 480;  // End the turn shortly after the final word
    const VAD_MIN_SPEECH_RMS = 4.5;          // Avoid treating quiet room noise as speech
    const VAD_MIN_END_RMS = 3.0;             // Keep soft word endings without a long hangover
    const VAD_NOISE_MARGIN = 2.5;            // Adaptive margin over the measured room noise
    const VAD_END_MARGIN = 1.2;
    const VAD_SPEECH_ONSET_FRAMES = 2;       // 80 ms at the 40 ms VAD interval
    const BARGE_IN_ENERGY_THRESHOLD = 18;    // Higher threshold avoids TTS speaker echo
    const BARGE_IN_HOLD_MS = 160;            // Require sustained speech before interrupting
    const BARGE_IN_GRACE_MS = 450;           // Let playback begin before monitoring

    // ── DOM Elements ──
    const orb            = document.getElementById('orb');
    const orbLabel       = document.getElementById('orb-label');
    const statusText     = document.getElementById('status');
    const levelBar       = document.getElementById('level');
    const transcriptFeed = document.getElementById('transcript');
    const languageSelect = document.getElementById('language-select');
    const speakerSelect  = document.getElementById('speaker-select');
    const bargeInCheck   = document.getElementById('barge-in');
    const btnResetChat   = document.getElementById('btn-reset-chat');
    const btnResetHdr    = document.getElementById('btn-reset-session');
    const textForm       = document.getElementById('composer');
    const textInput      = document.getElementById('text-input');
    const ttsPlayer      = document.getElementById('tts-audio-player');
    const apiStatusText  = document.getElementById('api-status-text');
    const apiStatusBadge = document.getElementById('api-status-badge');

    // Booking & Lookup DOM
    const btnTriggerExpertModal = document.getElementById('btn-trigger-expert-modal');
    const expertModalBackdrop   = document.getElementById('expert-modal-backdrop');
    const btnCloseExpertModal   = document.getElementById('btn-close-expert-modal');
    const btnCancelExpertModal  = document.getElementById('btn-cancel-expert-modal');
    const expertBookingForm     = document.getElementById('expert-booking-form');
    const bookingName           = document.getElementById('booking-name');
    const bookingPhone          = document.getElementById('booking-phone');
    const bookingDate           = document.getElementById('booking-date');
    const bookingTime           = document.getElementById('booking-time');
    const bookingIssue          = document.getElementById('booking-issue');

    const btnOpenLookup        = document.getElementById('btn-open-lookup');
    const lookupModalBackdrop  = document.getElementById('lookup-modal-backdrop');
    const btnCloseLookupModal  = document.getElementById('btn-close-lookup-modal');
    const lookupRefInput       = document.getElementById('lookup-ref-input');
    const btnSearchRef         = document.getElementById('btn-search-ref');
    const lookupResultBox      = document.getElementById('lookup-result-box');

    // Test-drive booking DOM
    const btnTriggerTestDrive  = document.getElementById('btn-trigger-test-drive');
    const testDriveBackdrop    = document.getElementById('test-drive-modal-backdrop');
    const btnCloseTestDrive    = document.getElementById('btn-close-test-drive');
    const testDriveForm        = document.getElementById('test-drive-form');
    const tdDealer             = document.getElementById('td-dealer');
    const tdModel              = document.getElementById('td-model');
    const tdModelDetails       = document.getElementById('td-model-details');
    const tdDate               = document.getElementById('td-date');
    const tdTime               = document.getElementById('td-time');
    const tdSlotStatus         = document.getElementById('td-slot-status');
    const tdName               = document.getElementById('td-name');
    const tdMobile             = document.getElementById('td-mobile');
    const tdEmail              = document.getElementById('td-email');
    const tdAddress            = document.getElementById('td-address');
    const tdCity               = document.getElementById('td-city');
    const tdState              = document.getElementById('td-state');
    const tdPincode            = document.getElementById('td-pincode');
    const tdNotes              = document.getElementById('td-notes');
    const tdConsent            = document.getElementById('td-consent');
    const tdReview             = document.getElementById('td-review');
    const tdFormError          = document.getElementById('td-form-error');
    const tdBack               = document.getElementById('td-back');
    const tdNext               = document.getElementById('td-next');
    const tdSubmit             = document.getElementById('td-submit');

    // ── Phase Machine ──
    const PHASES = {
        idle: { label: "Tap to talk", status: "Not connected — tap the orb to start live call" },
        connecting: { label: "Connecting", status: "Opening audio stream & initializing Sarvam AI…" },
        listening: { label: "Listening", status: "Just start speaking — no button to hold" },
        hearing: { label: "Listening", status: "Hearing you speak…" },
        thinking: { label: "Thinking", status: "Analyzing vehicle fault with sarvam-105b…" },
        speaking: { label: "Speaking", status: "Talk over me any time to interrupt" }
    };

    function setPhase(newPhase) {
        phase = newPhase;
        const info = PHASES[newPhase] || PHASES.idle;
        orb.dataset.phase = newPhase;
        orbLabel.textContent = info.label;
        statusText.textContent = assistantMode === 'TEST_DRIVE' && newPhase === 'thinking'
            ? 'Checking Maruti models, dealers and test-drive availability…'
            : info.status;
    }

    // ── Init ──
    checkSystemStatus();
    initializeTestDriveBooking();
    applyAssistantModeUI(assistantMode === 'TEST_DRIVE');

    // ── Event Listeners ──
    orb.addEventListener('click', () => (isRunning ? stopCall() : startCall()));
    languageSelect.addEventListener('change', e => { selectedLanguage = e.target.value; });
    speakerSelect.addEventListener('change', e => { selectedSpeaker = e.target.value; });

    btnResetChat.addEventListener('click', resetSession);
    btnResetHdr.addEventListener('click', resetSession);

    textForm.addEventListener('submit', e => {
        e.preventDefault();
        const txt = textInput.value.trim();
        if (txt) { sendTextMessage(txt); textInput.value = ''; }
    });

    bindQuickPromptButtons();

    // Modals
    btnTriggerExpertModal.addEventListener('click', () => openBookingModal());
    btnCloseExpertModal.addEventListener('click', closeBookingModal);
    btnCancelExpertModal.addEventListener('click', closeBookingModal);

    btnOpenLookup.addEventListener('click', () => {
        lookupModalBackdrop.classList.add('active');
        lookupRefInput.focus();
    });
    btnCloseLookupModal.addEventListener('click', () => {
        lookupModalBackdrop.classList.remove('active');
    });

    expertBookingForm.addEventListener('submit', async e => {
        e.preventDefault();
        await submitExpertBooking();
    });

    btnSearchRef.addEventListener('click', lookupBookingRef);
    lookupRefInput.addEventListener('keypress', e => {
        if (e.key === 'Enter') { e.preventDefault(); lookupBookingRef(); }
    });

    btnTriggerTestDrive.addEventListener('click', toggleTestDriveMode);
    btnCloseTestDrive.addEventListener('click', closeTestDriveBooking);
    tdBack.addEventListener('click', () => showTestDriveStep(testDriveStep - 1));
    tdNext.addEventListener('click', () => {
        if (validateTestDriveStep(testDriveStep)) {
            showTestDriveStep(testDriveStep + 1);
        }
    });
    tdDealer.addEventListener('change', loadDealerCars);
    tdModel.addEventListener('change', () => {
        renderSelectedModel();
        if (tdDate.value) loadTestDriveAvailability();
    });
    tdDate.addEventListener('change', loadTestDriveAvailability);
    testDriveForm.addEventListener('submit', submitTestDriveBooking);
    document.querySelectorAll('input[name="td-location"]').forEach(input => {
        input.addEventListener('change', () => {
            document.querySelectorAll('.location-option').forEach(option => {
                option.classList.toggle('selected', option.contains(input) && input.checked);
            });
        });
    });

    // ── System Health ──
    async function checkSystemStatus() {
        try {
            const res = await fetch('/api/health');
            if (res.ok) {
                const data = await res.json();
                const sv = data.sarvam_ai;
                if (sv && sv.is_live) {
                    apiStatusText.innerHTML = `LIVE &mdash; ${sv.stt_model} | ${sv.llm_model} | ${sv.tts_model}`;
                } else {
                    apiStatusText.textContent = 'DEMO MODE';
                }
            }
        } catch {
            apiStatusText.textContent = 'SYS ERROR';
        }
    }

    // ── ASSISTANT MODE & PROACTIVE GREETING ──
    async function toggleTestDriveMode() {
        assistantMode = assistantMode === 'TEST_DRIVE' ? 'DIAGNOSTIC' : 'TEST_DRIVE';
        localStorage.setItem('car_ai_assistant_mode', assistantMode);
        testDriveWelcomed = false;
        stopCall();
        try {
            await fetch('/api/reset-session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId })
            });
        } catch {}
        applyAssistantModeUI(true);
    }

    function applyAssistantModeUI(resetFeed = false) {
        const isTestDrive = assistantMode === 'TEST_DRIVE';
        btnTriggerTestDrive.classList.toggle('mode-active', isTestDrive);
        btnTriggerTestDrive.innerHTML = isTestDrive
            ? '<i class="fa-solid fa-circle-check"></i><span>Test Drive Mode Active</span>'
            : '<i class="fa-solid fa-key"></i><span>Book Maruti Test Drive</span>';
        btnTriggerTestDrive.title = isTestDrive
            ? 'Click to return to car diagnostic mode'
            : 'Switch the voice assistant to Maruti test-drive mode';
        textInput.placeholder = isTestDrive
            ? '…or type your Maruti buying or test-drive question'
            : '…or type vehicle fault instead';
        orbLabel.textContent = 'Tap to talk';
        statusText.textContent = isTestDrive
            ? 'Test-drive mode ready — tap the orb and the Maruti concierge will greet you'
            : 'Not connected — tap the orb to start live call';

        if (resetFeed) {
            transcriptFeed.innerHTML = isTestDrive
                ? `<div class="empty-state">
                    <i class="fa-solid fa-key empty-icon"></i>
                    <p class="empty">Test-drive mode is active. Tap the orb to hear your Maruti welcome.</p>
                    <div class="quick-symptoms-bar">
                        <span class="symptom-preset" data-symptom="मुझे नई लॉन्च हुई मारुति कारें बताइए जो टेस्ट ड्राइव के लिए उपलब्ध हैं।">New launches</span>
                        <span class="symptom-preset" data-symptom="मेरा बजट 15 लाख रुपये है, मेरे लिए कौन सी मारुति कार सही रहेगी?">₹15 lakh budget</span>
                    </div>
                </div>`
                : `<div class="empty-state">
                    <i class="fa-solid fa-comment-dots empty-icon"></i>
                    <p class="empty">Diagnostic mode is active. Tell me what is happening with your car.</p>
                </div>`;
            bindQuickPromptButtons();
        }
    }

    async function playAssistantWelcome() {
        if (testDriveWelcomed) {
            startVADListeningTurn();
            return;
        }
        testDriveWelcomed = true;
        setPhase('thinking');
        try {
            const query = new URLSearchParams({
                assistant_mode: assistantMode,
                language_code: selectedLanguage,
                speaker: selectedSpeaker
            });
            const response = await fetch(`/api/assistant/welcome?${query}`);
            if (!response.ok) throw new Error(await getApiError(response, 'Could not start the welcome message.'));
            const data = await response.json();
            const playButton = renderSalesWelcome(data.message, data.audio_b64, data.audio_url);
            playAudio(data.audio_b64, data.message, playButton, data.audio_url);
        } catch (error) {
            console.error(error);
            renderErrorCard(error.message || 'Could not play the welcome message.');
            startVADListeningTurn();
        }
    }

    function renderSalesWelcome(message, audioB64, audioUrl) {
        removeEmptyState();
        const audioId = 'welcome_tts_' + Math.random().toString(36).substr(2, 7);
        const bubble = document.createElement('div');
        bubble.className = 'bubble assistant';
        bubble.innerHTML = `
            <span class="who" style="color:var(--accent-blue)">MARUTI CUSTOMER CONCIERGE &nbsp;·&nbsp; ${getTime()}</span>
            <div class="ai-report-card sales-report-card">
                <div class="report-card-header">
                    <span class="report-card-brand" style="color:var(--accent-blue)">
                        <i class="fa-solid fa-car-side"></i> WELCOME TO MARUTI SUZUKI
                    </span>
                    <span class="report-card-time">${getTime()}</span>
                </div>
                <div class="report-summary-block">${esc(message)}</div>
                <button class="btn-book-expert-inline sales-booking-button" type="button">
                    <i class="fa-solid fa-calendar-plus"></i>
                    <span>OPEN TEST-DRIVE BOOKING FORM</span>
                </button>
                <div class="tts-strip">
                    <button class="tts-play-btn" id="${audioId}_btn" title="Play welcome message">
                        <i class="fa-solid fa-play"></i>
                    </button>
                    <span>SARVAM TTS &mdash; TAP TO REPLAY WELCOME</span>
                </div>
            </div>`;
        bubble.querySelector('.sales-booking-button').addEventListener('click', openTestDriveBooking);
        transcriptFeed.appendChild(bubble);
        const playButton = document.getElementById(`${audioId}_btn`);
        playButton?.addEventListener('click', () => playAudio(audioB64, message, playButton, audioUrl));
        scrollToBottom();
        return playButton;
    }

    // ── MARUTI TEST-DRIVE BOOKING ──
    async function initializeTestDriveBooking() {
        const today = new Date();
        const maxDate = new Date(today);
        maxDate.setDate(maxDate.getDate() + 30);
        tdDate.min = localDateValue(today);
        tdDate.max = localDateValue(maxDate);
        tdDate.value = localDateValue(today);
        try {
            const response = await fetch('/api/dealerships?city=New%20Delhi');
            if (!response.ok) throw new Error(await getApiError(response, 'Could not load dealerships.'));
            const data = await response.json();
            testDriveDealers = data.dealerships || [];

            tdDealer.innerHTML = '<option value="">Select a dealership</option>';
            testDriveDealers.forEach(dealer => {
                const option = document.createElement('option');
                option.value = String(dealer.id);
                option.textContent = `${dealer.channel} · ${dealer.name} — ${dealer.address}`;
                tdDealer.appendChild(option);
            });
        } catch (error) {
            console.error(error);
            tdDealer.innerHTML = '<option value="">Dealerships unavailable</option>';
            showTestDriveError(error.message || 'Could not load dealerships.');
        }
    }

    function openTestDriveBooking() {
        if (isRunning) stopCall();
        showTestDriveStep(1);
        testDriveBackdrop.classList.add('active');
        setTimeout(() => tdDealer.focus(), 100);
    }

    function closeTestDriveBooking() {
        testDriveBackdrop.classList.remove('active');
        clearTestDriveError();
    }

    async function loadDealerCars() {
        const dealershipId = tdDealer.value;
        testDriveCars = [];
        tdModel.innerHTML = '<option value="">Loading cars…</option>';
        tdModel.disabled = true;
        tdModelDetails.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Loading dealerwise Maruti inventory…</span>';
        tdTime.innerHTML = '<option value="">Choose a car and date first</option>';
        tdTime.disabled = true;

        if (!dealershipId) {
            tdModel.innerHTML = '<option value="">Select a dealership first</option>';
            tdModelDetails.innerHTML = '<i class="fa-solid fa-circle-info"></i><span>Select a dealer and car to see model details, indicative price and stock.</span>';
            return;
        }

        try {
            const response = await fetch(`/api/cars?dealership_id=${encodeURIComponent(dealershipId)}`);
            if (!response.ok) throw new Error(await getApiError(response, 'Could not load cars.'));
            const data = await response.json();
            testDriveCars = data.cars || [];

            tdModel.innerHTML = '<option value="">Select a car model</option>';
            testDriveCars.forEach(car => {
                const option = document.createElement('option');
                option.value = String(car.id);
                option.textContent = `${car.name} · ${car.body_type} · from ${formatINR(car.starting_price)}`;
                tdModel.appendChild(option);
            });
            tdModel.disabled = testDriveCars.length === 0;
            tdModelDetails.innerHTML = testDriveCars.length
                ? '<i class="fa-solid fa-car"></i><span>Select a model to see price, fuel, transmission and dealer stock.</span>'
                : '<i class="fa-solid fa-triangle-exclamation"></i><span>No cars are configured for this dealership.</span>';
        } catch (error) {
            console.error(error);
            tdModel.innerHTML = '<option value="">Cars unavailable</option>';
            tdModelDetails.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i><span>${esc(error.message)}</span>`;
        }
    }

    function renderSelectedModel() {
        const car = testDriveCars.find(item => String(item.id) === tdModel.value);
        if (!car) {
            tdModelDetails.innerHTML = '<i class="fa-solid fa-car"></i><span>Select a model to see price, fuel, transmission and dealer stock.</span>';
            return;
        }

        const price = car.maximum_price
            ? `${formatINR(car.starting_price)} – ${formatINR(car.maximum_price)}`
            : `From ${formatINR(car.starting_price)}`;
        const note = car.price_note ? `<div>${esc(car.price_note)}</div>` : '';
        tdModelDetails.innerHTML = `
            <i class="fa-solid fa-car-side"></i>
            <div>
                <div class="model-details-title">
                    <span>${esc(car.name)} · ${esc(car.body_type)}</span>
                    <span class="inventory-chip">${esc(String(car.sale_quantity))} sale units · ${esc(String(car.test_drive_quantity))} test-drive cars</span>
                </div>
                <div>${esc(car.description)}</div>
                ${note}
                <div class="model-meta">
                    <span><i class="fa-solid fa-indian-rupee-sign"></i> ${esc(price)}</span>
                    <span><i class="fa-solid fa-gas-pump"></i> ${esc(car.fuel_types.join(', '))}</span>
                    <span><i class="fa-solid fa-gears"></i> ${esc(car.transmission_types.join(', '))}</span>
                    <span><i class="fa-solid fa-users"></i> ${esc(String(car.seating_capacity))} seats</span>
                </div>
            </div>`;
    }

    async function loadTestDriveAvailability() {
        if (!tdDealer.value || !tdModel.value || !tdDate.value) {
            tdTime.innerHTML = '<option value="">Choose dealer, car and date first</option>';
            tdTime.disabled = true;
            return;
        }

        tdTime.innerHTML = '<option value="">Checking live availability…</option>';
        tdTime.disabled = true;
        tdSlotStatus.className = 'slot-status';
        tdSlotStatus.textContent = 'Checking the dealer test-drive fleet…';

        try {
            const query = new URLSearchParams({
                dealership_id: tdDealer.value,
                car_model_id: tdModel.value,
                booking_date: tdDate.value
            });
            const response = await fetch(`/api/test-drive/availability?${query}`);
            if (!response.ok) throw new Error(await getApiError(response, 'Could not load test-drive slots.'));
            const data = await response.json();
            const availableSlots = (data.slots || []).filter(slot => slot.available_quantity > 0);

            tdTime.innerHTML = '<option value="">Select an available time</option>';
            availableSlots.forEach(slot => {
                const option = document.createElement('option');
                option.value = slot.time_slot;
                option.textContent = `${slot.time_slot} — ${slot.available_quantity} vehicle${slot.available_quantity === 1 ? '' : 's'} available`;
                tdTime.appendChild(option);
            });
            tdTime.disabled = availableSlots.length === 0;
            tdSlotStatus.className = `slot-status ${availableSlots.length ? 'available' : 'unavailable'}`;
            tdSlotStatus.innerHTML = availableSlots.length
                ? `<i class="fa-solid fa-circle-check"></i> ${availableSlots.length} time slot${availableSlots.length === 1 ? '' : 's'} available on this date.`
                : '<i class="fa-solid fa-circle-xmark"></i> No test-drive vehicle is available on this date. Please choose another date.';
        } catch (error) {
            console.error(error);
            tdTime.innerHTML = '<option value="">Availability unavailable</option>';
            tdSlotStatus.className = 'slot-status unavailable';
            tdSlotStatus.textContent = error.message || 'Could not load availability.';
        }
    }

    function showTestDriveStep(step) {
        testDriveStep = Math.min(4, Math.max(1, step));
        document.querySelectorAll('.test-drive-step').forEach(section => {
            section.classList.toggle('active', Number(section.dataset.step) === testDriveStep);
        });
        document.querySelectorAll('.booking-progress-item').forEach(item => {
            const itemStep = Number(item.dataset.progressStep);
            item.classList.toggle('active', itemStep === testDriveStep);
            item.classList.toggle('complete', itemStep < testDriveStep);
        });
        tdBack.hidden = testDriveStep === 1;
        tdNext.hidden = testDriveStep === 4;
        tdSubmit.hidden = testDriveStep !== 4;
        clearTestDriveError();

        if (testDriveStep === 2 && tdDate.value) {
            loadTestDriveAvailability();
        }
        if (testDriveStep === 4) {
            renderTestDriveReview();
        }
    }

    function validateTestDriveStep(step) {
        clearTestDriveError();
        if (step === 1) {
            if (!tdDealer.value || !tdModel.value) {
                showTestDriveError('Please select both a dealership and a Maruti model.');
                return false;
            }
        }
        if (step === 2) {
            if (!tdDate.value || !tdTime.value) {
                showTestDriveError('Please select an available date and time.');
                return false;
            }
        }
        if (step === 3) {
            const mobileDigits = tdMobile.value.replace(/\D/g, '').replace(/^91(?=\d{10}$)/, '');
            if (!tdName.value.trim() || !tdAddress.value.trim() || !tdCity.value.trim() || !tdState.value.trim()) {
                showTestDriveError('Name and complete address are required.');
                return false;
            }
            if (!/^[6-9]\d{9}$/.test(mobileDigits)) {
                showTestDriveError('Enter a valid 10-digit Indian mobile number.');
                return false;
            }
            if (!/^\d{6}$/.test(tdPincode.value.trim())) {
                showTestDriveError('Enter a valid 6-digit pincode.');
                return false;
            }
            if (tdEmail.value && !tdEmail.checkValidity()) {
                showTestDriveError('Enter a valid email address or leave it blank.');
                return false;
            }
        }
        return true;
    }

    function validateTestDriveConfirmation() {
        if (!tdConsent.checked) {
            showTestDriveError('Please provide consent before confirming the booking.');
            return false;
        }
        return true;
    }

    function renderTestDriveReview() {
        const dealer = testDriveDealers.find(item => String(item.id) === tdDealer.value);
        const car = testDriveCars.find(item => String(item.id) === tdModel.value);
        const location = getSelectedTestDriveLocation();
        tdReview.innerHTML = `
            <div><span>Customer</span><strong>${esc(tdName.value.trim())}</strong></div>
            <div><span>Car</span><strong>${esc(car?.name || '')}</strong></div>
            <div><span>Dealer</span><strong>${esc(dealer?.name || '')}</strong></div>
            <div><span>Date & time</span><strong>${esc(tdDate.value)} · ${esc(tdTime.value)}</strong></div>
            <div><span>Location</span><strong>${location === 'HOME' ? 'Customer home' : 'Selected dealership'}</strong></div>
            <div><span>Documents to carry</span><strong>Original driving licence + Aadhaar or PAN</strong></div>`;
    }

    async function submitTestDriveBooking(event) {
        event.preventDefault();
        clearTestDriveError();
        if (!validateTestDriveStep(3) || !validateTestDriveConfirmation()) return;

        tdSubmit.disabled = true;
        tdSubmit.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> RESERVING SLOT…';
        const payload = {
            full_name: tdName.value.trim(),
            mobile: tdMobile.value.trim(),
            email: tdEmail.value.trim() || null,
            address_line: tdAddress.value.trim(),
            city: tdCity.value.trim(),
            state: tdState.value.trim(),
            pincode: tdPincode.value.trim(),
            dealership_id: Number(tdDealer.value),
            car_model_id: Number(tdModel.value),
            booking_date: tdDate.value,
            time_slot: tdTime.value,
            location_type: getSelectedTestDriveLocation(),
            customer_notes: tdNotes.value.trim() || null,
            consent_given: tdConsent.checked
        };

        try {
            const response = await fetch('/api/test-drive/bookings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!response.ok) throw new Error(await getApiError(response, 'Could not reserve the test-drive slot.'));
            const booking = await response.json();
            closeTestDriveBooking();
            renderTestDriveConfirmation(booking);
            speakTestDriveConfirmation(booking);
            resetTestDriveForm();
        } catch (error) {
            console.error(error);
            showTestDriveError(error.message || 'Could not create the booking.');
        } finally {
            tdSubmit.disabled = false;
            tdSubmit.innerHTML = '<i class="fa-solid fa-circle-check"></i> CONFIRM TEST DRIVE';
        }
    }

    function renderTestDriveConfirmation(booking) {
        removeEmptyState();
        const bubble = document.createElement('div');
        bubble.className = 'bubble assistant';
        bubble.innerHTML = `
            <span class="who" style="color:var(--accent-blue)">MARUTI TEST DRIVE &nbsp;·&nbsp; ${getTime()}</span>
            <div class="ai-report-card test-drive-confirmation">
                <div class="report-card-header">
                    <span style="font-family:var(--font-mono); color:var(--accent-green); font-weight:700;">
                        <i class="fa-solid fa-circle-check"></i> TEST DRIVE CONFIRMED
                    </span>
                    <span style="font-family:var(--font-mono); font-weight:700; color:var(--accent-blue);">${esc(booking.reference_id)}</span>
                </div>
                <div class="test-drive-confirmation-grid">
                    <div><span>Customer</span><strong>${esc(booking.customer_name)}</strong></div>
                    <div><span>Car</span><strong>${esc(booking.car_model)}</strong></div>
                    <div><span>Dealer</span><strong>${esc(booking.dealership_name)}</strong></div>
                    <div><span>Date & time</span><strong>${esc(booking.booking_date)} · ${esc(booking.time_slot)}</strong></div>
                    <div><span>Location</span><strong>${esc(booking.location_type === 'HOME' ? 'Customer home' : 'Dealership')}</strong></div>
                    <div><span>Documents to carry</span><strong>Original driving licence + Aadhaar or PAN</strong></div>
                </div>
                <div class="privacy-notice">
                    <i class="fa-solid fa-location-dot"></i>
                    <span>${esc(booking.test_drive_address)}</span>
                </div>
                <div style="font-size:0.8rem; color:var(--text-primary);">${esc(booking.confirmation_message)}</div>
            </div>`;
        transcriptFeed.appendChild(bubble);
        scrollToBottom();
    }

    async function speakTestDriveConfirmation(booking) {
        const confirmation = selectedLanguage.startsWith('hi')
            ? (
                `आपकी टेस्ट ड्राइव बुकिंग आईडी ${booking.reference_id} है। `
                + `यही बुकिंग जानकारी आपको आपके रजिस्टर्ड मोबाइल नंबर पर एस एम एस `
                + `के माध्यम से भी मिलेगी।`
            )
            : booking.confirmation_message;
        try {
            const response = await fetch('/api/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: confirmation,
                    language_code: selectedLanguage,
                    speaker: selectedSpeaker
                })
            });
            if (!response.ok) {
                throw new Error(await getApiError(response, 'Could not generate booking confirmation audio.'));
            }
            const audio = await response.json();
            await playAudio(audio.audio_b64, confirmation, null, audio.audio_url);
        } catch (error) {
            console.warn('Test-drive confirmation TTS failed; using browser voice.', error);
            await playAudio(null, confirmation, null);
        }
    }

    function resetTestDriveForm() {
        testDriveForm.reset();
        tdCity.value = 'New Delhi';
        tdState.value = 'Delhi';
        tdModel.innerHTML = '<option value="">Select a dealership first</option>';
        tdModel.disabled = true;
        tdTime.innerHTML = '<option value="">Choose a date first</option>';
        tdTime.disabled = true;
        tdDate.value = localDateValue(new Date());
        testDriveCars = [];
        document.querySelectorAll('.location-option').forEach(option => {
            const input = option.querySelector('input');
            option.classList.toggle('selected', input.value === 'HOME');
        });
        showTestDriveStep(1);
    }

    function getSelectedTestDriveLocation() {
        return document.querySelector('input[name="td-location"]:checked')?.value || 'HOME';
    }

    function showTestDriveError(message) {
        tdFormError.textContent = message;
        tdFormError.classList.add('active');
    }

    function clearTestDriveError() {
        tdFormError.textContent = '';
        tdFormError.classList.remove('active');
    }

    function formatINR(amount) {
        return new Intl.NumberFormat('en-IN', {
            style: 'currency',
            currency: 'INR',
            maximumFractionDigits: 0
        }).format(Number(amount || 0));
    }

    function localDateValue(value) {
        const year = value.getFullYear();
        const month = String(value.getMonth() + 1).padStart(2, '0');
        const day = String(value.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    // ── START REAL-TIME CALL (PRIME AUDIO + MIC + VAD) ──
    async function startCall() {
        setPhase('connecting');

        try {
            // 1. Prime AudioContext on user gesture (fixes Chrome/Safari autoplay policy)
            if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            if (audioCtx.state === 'suspended') await audioCtx.resume();

            // Prime HTML5 Audio element
            ttsPlayer.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=";
            ttsPlayer.play().catch(() => {});

            // 2. Open Mic Stream
            micStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });

            setupVADAnalyser(micStream);
            isRunning = true;
            if (assistantMode === 'TEST_DRIVE') {
                await playAssistantWelcome();
            } else {
                setPhase('listening');
                startVADListeningTurn();
            }

        } catch (err) {
            console.error(err);
            alert('Microphone access is required for live voice call. Please check browser permissions.');
            setPhase('idle');
        }
    }

    function stopCall() {
        isRunning = false;
        testDriveWelcomed = false;
        stopPlayback();

        if (vadCheckInterval) clearInterval(vadCheckInterval);
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            try { mediaRecorder.stop(); } catch {}
        }
        if (micStream) {
            micStream.getTracks().forEach(t => t.stop());
            micStream = null;
        }
        stopVisualizer();
        setPhase('idle');
    }

    // ── AUDIO CONTEXT & VAD ANALYSER ──
    function setupVADAnalyser(stream) {
        if (analyserNode) analyserNode.disconnect();
        analyserNode = audioCtx.createAnalyser();
        analyserNode.fftSize = 256;
        // The default 0.8 smoothing keeps old speech energy alive for seconds.
        // A short smoothing window lets end-of-speech detection react promptly.
        analyserNode.smoothingTimeConstant = 0.12;
        const source = audioCtx.createMediaStreamSource(stream);
        source.connect(analyserNode);
        drawLevelMeter();
    }

    function drawLevelMeter() {
        if (!analyserNode) return;
        const buf = analyserNode.frequencyBinCount;
        const arr = new Uint8Array(buf);
        function loop() {
            visualizerAnimationId = requestAnimationFrame(loop);
            analyserNode.getByteFrequencyData(arr);
            let sum = 0;
            for (let i = 0; i < buf; i++) sum += arr[i];
            const avg = sum / buf;
            const norm = Math.min(1, avg / 60);
            levelBar.style.transform = `scaleX(${norm})`;
        }
        if (visualizerAnimationId) cancelAnimationFrame(visualizerAnimationId);
        loop();
    }

    function stopVisualizer() {
        if (visualizerAnimationId) cancelAnimationFrame(visualizerAnimationId);
        levelBar.style.transform = 'scaleX(0)';
    }

    // ── VAD TURN TAKING ──
    function startVADListeningTurn() {
        if (!isRunning) return;

        audioChunks = [];
        speechDetected = false;
        silenceStartTimestamp = null;
        vadNoiseFloor = 2;
        vadSpeechFrames = 0;
        lastSpeechTimestamp = null;
        setPhase('listening');

        const supportedMimeType = [
            'audio/webm;codecs=opus',
            'audio/mp4;codecs=mp4a.40.2',
            'audio/mp4',
            'audio/webm'
        ].find(type => MediaRecorder.isTypeSupported(type));
        const options = supportedMimeType ? { mimeType: supportedMimeType } : {};
        mediaRecorder = new MediaRecorder(micStream, options);
        const recorder = mediaRecorder;

        recorder.ondataavailable = e => {
            if (e.data.size > 0) audioChunks.push(e.data);
        };

        recorder.onstop = async () => {
            if (vadCheckInterval) clearInterval(vadCheckInterval);
            vadCheckInterval = null;
            if (maxRecordingTimeout) {
                clearTimeout(maxRecordingTimeout);
                maxRecordingTimeout = null;
            }
            if (!isRunning) return;

            const blob = new Blob(audioChunks, {
                type: recorder.mimeType || supportedMimeType || 'application/octet-stream'
            });
            if (blob.size > 1200 && speechDetected) {
                setPhase('thinking');
                await processVoiceAudio(blob);
            } else if (isRunning) {
                // Background click / false alarm -> resume listening turn
                startVADListeningTurn();
            }
        };

        if (maxRecordingTimeout) clearTimeout(maxRecordingTimeout);
        maxRecordingTimeout = setTimeout(() => {
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.stop();
            }
        }, 15000);

        // Safari produces fragmented MP4 chunks when a timeslice is supplied.
        // Let MediaRecorder emit one complete, readable file when stop() is called.
        recorder.start();

        if (vadCheckInterval) clearInterval(vadCheckInterval);
        vadCheckInterval = setInterval(checkVADVolume, 40);
    }

    function checkVADVolume() {
        if (!analyserNode || !isRunning || phase === 'thinking') return;

        const buf = analyserNode.frequencyBinCount;
        const arr = new Uint8Array(buf);
        analyserNode.getByteFrequencyData(arr);

        let sum = 0;
        for (let i = 0; i < buf; i++) sum += arr[i];
        const avgEnergy = sum / buf;

        // BARGE-IN: keep monitoring the microphone while TTS is playing.
        if (phase === 'speaking') {
            if (!bargeInCheck.checked || avgEnergy <= BARGE_IN_ENERGY_THRESHOLD) {
                bargeInSpeechStart = null;
                return;
            }

            if (!bargeInSpeechStart) {
                bargeInSpeechStart = Date.now();
                return;
            }

            if (Date.now() - bargeInSpeechStart >= BARGE_IN_HOLD_MS) {
                bargeInSpeechStart = null;
                stopPlayback();
                startVADListeningTurn();
            }
            return;
        }

        if (phase === 'speaking' || phase === 'thinking') return;

        const timeDomain = new Uint8Array(analyserNode.fftSize);
        analyserNode.getByteTimeDomainData(timeDomain);
        let squareSum = 0;
        for (let i = 0; i < timeDomain.length; i++) {
            const centered = timeDomain[i] - 128;
            squareSum += centered * centered;
        }
        const rmsEnergy = Math.sqrt(squareSum / timeDomain.length);
        const speechThreshold = Math.max(
            VAD_MIN_SPEECH_RMS,
            vadNoiseFloor + VAD_NOISE_MARGIN
        );
        const endThreshold = Math.max(
            VAD_MIN_END_RMS,
            vadNoiseFloor + VAD_END_MARGIN
        );
        const now = Date.now();

        if (!speechDetected) {
            if (rmsEnergy > speechThreshold) {
                vadSpeechFrames++;
            } else {
                vadSpeechFrames = 0;
                // Learn the current room level only while speech has not started.
                vadNoiseFloor = Math.min(
                    8,
                    Math.max(1, (vadNoiseFloor * 0.9) + (rmsEnergy * 0.1))
                );
            }

            if (vadSpeechFrames >= VAD_SPEECH_ONSET_FRAMES) {
                speechDetected = true;
                lastSpeechTimestamp = now;
                silenceStartTimestamp = null;
                setPhase('hearing');
            }
            return;
        }

        if (rmsEnergy > endThreshold) {
            lastSpeechTimestamp = now;
            silenceStartTimestamp = null;
            return;
        }

        if (!silenceStartTimestamp) {
            silenceStartTimestamp = now;
        }
        if (
            lastSpeechTimestamp
            && now - lastSpeechTimestamp >= SILENCE_DURATION_THRESHOLD
        ) {
            // Stop the listening UI immediately; MediaRecorder then flushes
            // the complete browser audio file before the API request starts.
            setPhase('thinking');
            if (vadCheckInterval) {
                clearInterval(vadCheckInterval);
                vadCheckInterval = null;
            }
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.stop();
            }
        }
    }

    // ── API COMMUNICATIONS ──
    async function getApiError(response, fallback) {
        try {
            const body = await response.json();
            if (Array.isArray(body.detail)) {
                return body.detail.map(item => item.msg || String(item)).join(' ');
            }
            const detail = body.detail || body.message || fallback;
            if (
                response.status === 402
                || (
                    typeof detail === 'string'
                    && /no credits|credits are exhausted|insufficient[_ ]quota/i.test(detail)
                )
            ) {
                return 'Sarvam AI credits are exhausted. Add credits to the configured Sarvam account, then tap the orb to reconnect.';
            }
            if (typeof detail === 'string' && detail.includes('duration exceeds maximum limit')) {
                return 'The recording was too long. Please speak for less than 15 seconds and try again.';
            }
            if (typeof detail === 'string' && detail.includes('Failed to read the file')) {
                return 'The browser audio could not be read. Please retry the voice call.';
            }
            if (typeof detail === 'string' && detail.includes('Invalid file type')) {
                return 'The browser audio format was rejected. Please refresh the page and retry.';
            }
            return detail;
        } catch {
            return fallback;
        }
    }

    function isQuotaError(error) {
        return /credits are exhausted|no credits|insufficient[_ ]quota/i.test(
            error?.message || String(error || '')
        );
    }

    function showQuotaRequired() {
        stopCall();
        apiStatusBadge?.classList.add('quota');
        apiStatusText.textContent = 'CREDITS REQUIRED — SARVAM';
        if (transcriptFeed.querySelector('[data-quota-notice="true"]')) return;

        const bubble = document.createElement('div');
        bubble.className = 'bubble assistant';
        bubble.dataset.quotaNotice = 'true';
        bubble.innerHTML = `
            <span class="who" style="color:var(--accent-amber)">SARVAM ACCOUNT NOTICE</span>
            <div class="ai-report-card" style="border-left-color:var(--accent-amber); padding:0.75rem;">
                <div style="color:var(--text-primary); font-size:0.82rem; line-height:1.5;">
                    Sarvam AI credits are exhausted. Add credits to the configured Sarvam account,
                    then tap the orb to reconnect. Voice listening has been stopped so this notice
                    will not repeat.
                </div>
            </div>`;
        transcriptFeed.appendChild(bubble);
        scrollToBottom();
    }

    async function sendTextMessage(text) {
        removeEmptyState();
        renderDriverBubble(text);
        setPhase('thinking');

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    message: text,
                    language_code: selectedLanguage,
                    speaker: selectedSpeaker,
                    assistant_mode: assistantMode
                })
            });
            if (!res.ok) throw new Error(await getApiError(res, `API error (${res.status})`));
            const data = await res.json();
            lastSummary = data.summary || text;
            renderAssistantReport(data);
        } catch (err) {
            console.error(err);
            if (isQuotaError(err)) {
                showQuotaRequired();
                return;
            }
            renderErrorCard(`SYSTEM FAULT — ${err.message || 'Please check the network connection.'}`);
            if (isRunning) setPhase('listening');
            else setPhase('idle');
        }
    }

    async function processVoiceAudio(blob) {
        removeEmptyState();
        const form = new FormData();
        const mimeType = (blob.type || '').toLowerCase();
        const extension = mimeType.includes('mp4') || mimeType.includes('m4a')
            ? 'm4a'
            : mimeType.includes('ogg')
                ? 'ogg'
                : mimeType.includes('mpeg')
                    ? 'mp3'
                    : mimeType.includes('wav')
                        ? 'wav'
                        : 'webm';
        form.append('file', blob, `speech.${extension}`);
        form.append('session_id', sessionId);
        form.append('language_code', selectedLanguage);
        form.append('speaker', selectedSpeaker);
        form.append('assistant_mode', assistantMode);

        try {
            const res = await fetch('/api/voice-transcribe', { method: 'POST', body: form });
            if (!res.ok) throw new Error(await getApiError(res, `Voice API error (${res.status})`));
            const data = await res.json();

            renderDriverBubble(data.transcription || 'Voice Query');
            lastSummary = data.summary || data.transcription || 'Vehicle Diagnosis';
            renderAssistantReport(data);
        } catch (err) {
            console.error(err);
            if (isQuotaError(err)) {
                showQuotaRequired();
                return;
            }
            renderErrorCard(`VOICE ASSISTANT ERROR — ${err.message || 'Please retry speaking.'}`);
            if (isRunning) startVADListeningTurn();
            else setPhase('idle');
        }
    }

    // ── RENDER & TRANSCRIPT ──
    function removeEmptyState() {
        const empty = transcriptFeed.querySelector('.empty-state');
        if (empty) empty.remove();
    }

    function renderDriverBubble(text) {
        turnCount++;
        const bubble = document.createElement('div');
        bubble.className = 'bubble user';
        bubble.innerHTML = `
            <span class="who">YOU &nbsp;·&nbsp; ${getTime()}</span>
            <p>${esc(text)}</p>`;
        transcriptFeed.appendChild(bubble);
        scrollToBottom();
    }

    function renderAssistantReport(data) {
        const isSales = (data.assistant_mode || assistantMode) === 'TEST_DRIVE';
        const urgency    = (data.urgency || 'CAUTION').toUpperCase();
        const confidence = (data.confidence || 'HIGH').toUpperCase();
        const steps      = data.steps || [];
        const summary    = data.summary || steps[0] || '';

        const urgencyClass = urgency.includes('PULL') || urgency.includes('CRITICAL') || urgency.includes('DANGER')
            ? 'critical' : urgency.includes('SAFE') ? 'safe' : 'caution';
        const urgencyIcon  = urgencyClass === 'critical' ? 'fa-solid fa-triangle-exclamation' : urgencyClass === 'safe' ? 'fa-solid fa-circle-check' : 'fa-solid fa-circle-exclamation';

        const confFilled = confidence === 'LOW' ? 3 : confidence === 'MEDIUM' ? 6 : 9;
        const segColor   = confidence === 'LOW' ? '#EF4444' : confidence === 'MEDIUM' ? '#FF9500' : '#00E676';
        const confBarHtml = Array.from({length: 9}, (_, i) =>
            `<div class="confidence-segment" style="${i < confFilled ? `background:${segColor}; box-shadow:0 0 4px ${segColor};` : ''}"></div>`
        ).join('');

        const stepsHtml = steps.map((step, i) => `
            <div class="diag-step-item" onclick="this.classList.toggle('checked')">
                <div class="diag-step-num">${isSales ? 'C' : 'S'}${String(i + 1).padStart(2,'0')}</div>
                <div class="diag-step-text">${esc(step.replace(/^Step\s*\d+[:\-]\s*/i, ''))}</div>
            </div>`).join('');

        const audioId = 'tts_' + Math.random().toString(36).substr(2, 7);

        const bubble = document.createElement('div');
        bubble.className = 'bubble assistant';
        bubble.innerHTML = `
            <span class="who">${isSales ? 'MARUTI CUSTOMER CONCIERGE' : 'CAR AI DOCTOR'} &nbsp;·&nbsp; ${getTime()}</span>
            <div class="ai-report-card ${isSales ? 'sales-report-card' : ''}">
                <div class="report-card-header">
                    <div class="report-card-brand" ${isSales ? 'style="color:var(--accent-blue)"' : ''}>
                        <i class="fa-solid ${isSales ? 'fa-car-side' : 'fa-stethoscope'}"></i>
                        ${isSales ? 'MARUTI SALES & TEST-DRIVE ASSISTANT' : 'DIAGNOSTIC REPORT'}
                    </div>
                    <span class="report-card-time">${getTime()}</span>
                </div>

                ${isSales ? '' : `<div class="alert-strip">
                    <div class="urgency-hmi-badge ${urgencyClass}">
                        <i class="${urgencyIcon}"></i> ${esc(urgency)}
                    </div>
                    <div class="confidence-hmi-strip">
                        <span>CONFIDENCE: <strong>${esc(confidence)}</strong></span>
                        <div class="confidence-bar">${confBarHtml}</div>
                    </div>
                </div>`}

                <div class="report-summary-block">
                    ${esc(summary)}
                </div>

                ${isSales ? '' : `<div class="diagnostic-steps-list">${stepsHtml}</div>`}

                ${isSales && data.booking_complete ? '' : `
                    <button class="btn-book-expert-inline ${isSales ? 'sales-booking-button' : ''}" type="button">
                        <i class="fa-solid ${isSales ? 'fa-key' : 'fa-calendar-check'}"></i>
                        <span>${isSales ? 'CONTINUE TEST-DRIVE BOOKING' : 'SCHEDULE MASTER MECHANIC CALL (GET REF ID)'}</span>
                    </button>
                `}

                <div class="tts-strip">
                    <button class="tts-play-btn" id="${audioId}_btn" title="Play spoken reply">
                        <i class="fa-solid fa-play"></i>
                    </button>
                    <span>SARVAM TTS &mdash; ${esc(selectedSpeaker.replace('Male','').replace('Female',''))} VOICE REPLY</span>
                </div>
            </div>`;

        transcriptFeed.appendChild(bubble);
        scrollToBottom();

        const playBtn = document.getElementById(`${audioId}_btn`);
        if (playBtn) {
            playBtn.addEventListener('click', () => playAudio(data.audio_b64, summary, playBtn, data.audio_url));
        }
        const bookBtn = bubble.querySelector('.btn-book-expert-inline');
        if (bookBtn) {
            bookBtn.addEventListener('click', () => {
                if (isSales) openTestDriveBooking();
                else openBookingModal(summary);
            });
        }

        if (data.audio_url || data.audio_b64) {
            playAudio(data.audio_b64, summary, playBtn, data.audio_url);
        }
        else if (isRunning) startVADListeningTurn();
    }

    function renderErrorCard(msg) {
        const bubble = document.createElement('div');
        bubble.className = 'bubble assistant';
        bubble.innerHTML = `
            <span class="who" style="color:var(--red-alert)">SYSTEM FAULT</span>
            <div class="ai-report-card" style="border-left-color:var(--red-alert); padding:0.75rem;">
                <div style="color:var(--red-alert); font-size:0.8rem; font-family:var(--font-mono);">${esc(msg)}</div>
            </div>`;
        transcriptFeed.appendChild(bubble);
        scrollToBottom();
    }

    // ── AUDIO PLAYBACK & AUTO-RESUME ──
    function armBargeInMonitor(token) {
        if (bargeInArmTimeout) clearTimeout(bargeInArmTimeout);
        bargeInArmTimeout = setTimeout(() => {
            bargeInArmTimeout = null;
            if (!isRunning || token !== playbackToken || phase !== 'speaking') return;
            bargeInSpeechStart = null;
            if (vadCheckInterval) clearInterval(vadCheckInterval);
            vadCheckInterval = setInterval(checkVADVolume, 40);
        }, BARGE_IN_GRACE_MS);
    }

    async function playAudio(b64, fallback, btn, audioUrl = null) {
        const token = ++playbackToken;
        setPhase('speaking');
        bargeInSpeechStart = null;
        if (vadCheckInterval) clearInterval(vadCheckInterval);
        vadCheckInterval = null;
        if (bargeInArmTimeout) {
            clearTimeout(bargeInArmTimeout);
            bargeInArmTimeout = null;
        }
        let finished = false;
        let fallbackStarted = false;

        const onEnd = () => {
            if (finished || token !== playbackToken) return;
            finished = true;
            currentAudioSource = null;
            bargeInSpeechStart = null;
            if (bargeInArmTimeout) {
                clearTimeout(bargeInArmTimeout);
                bargeInArmTimeout = null;
            }
            if (vadCheckInterval) {
                clearInterval(vadCheckInterval);
                vadCheckInterval = null;
            }
            if (btn) btn.innerHTML = '<i class="fa-solid fa-play"></i>';
            if (isRunning) {
                startVADListeningTurn();
            } else {
                setPhase('idle');
            }
        };

        const speakFallback = () => {
            if (fallbackStarted || token !== playbackToken) return;
            fallbackStarted = true;
            if (!('speechSynthesis' in window) || !fallback) {
                onEnd();
                return;
            }
            const u = new SpeechSynthesisUtterance(fallback);
            u.lang = selectedLanguage;
            u.onend = onEnd;
            u.onerror = onEnd;
            window.speechSynthesis.speak(u);
            armBargeInMonitor(token);
        };

        // Prefer a normal same-origin media URL. Safari handles this path more
        // reliably than large base64 data URLs or delayed Web Audio decoding.
        if (audioUrl) {
            try {
                ttsPlayer.src = audioUrl;
                ttsPlayer.load();
                if (btn) btn.innerHTML = '<i class="fa-solid fa-pause"></i>';
                ttsPlayer.onended = onEnd;
                ttsPlayer.onerror = null;
                await ttsPlayer.play();
                armBargeInMonitor(token);
                return;
            } catch (error) {
                console.warn('Streamed audio playback failed; trying decoded audio.', error);
            }
        }

        // The AudioContext was unlocked by the orb click, so this remains reliable
        // in Safari even after the async welcome/TTS request has completed.
        if (b64 && audioCtx) {
            try {
                if (audioCtx.state === 'suspended') await audioCtx.resume();
                const bytes = Uint8Array.from(atob(b64), char => char.charCodeAt(0));
                const audioBuffer = await audioCtx.decodeAudioData(bytes.buffer.slice(0));
                if (token !== playbackToken) return;

                const source = audioCtx.createBufferSource();
                source.buffer = audioBuffer;
                source.connect(audioCtx.destination);
                source.onended = onEnd;
                currentAudioSource = source;
                if (btn) btn.innerHTML = '<i class="fa-solid fa-pause"></i>';
                source.start(0);
                armBargeInMonitor(token);
                return;
            } catch (error) {
                console.warn('Web Audio playback failed; trying HTML audio.', error);
            }
        }

        if (token !== playbackToken) return;

        if (b64) {
            try {
                ttsPlayer.src = `data:audio/wav;base64,${b64}`;
                if (btn) btn.innerHTML = '<i class="fa-solid fa-pause"></i>';
                ttsPlayer.onended = onEnd;
                ttsPlayer.onerror = speakFallback;
                await ttsPlayer.play();
                armBargeInMonitor(token);
                return;
            } catch (error) {
                console.warn('HTML audio playback failed; using browser speech.', error);
            }
        }

        speakFallback();
    }

    function stopPlayback() {
        playbackToken++;
        if (bargeInArmTimeout) {
            clearTimeout(bargeInArmTimeout);
            bargeInArmTimeout = null;
        }
        if (currentAudioSource) {
            currentAudioSource.onended = null;
            try {
                currentAudioSource.stop();
                currentAudioSource.disconnect();
            } catch {}
            currentAudioSource = null;
        }
        try {
            ttsPlayer.onended = null;
            ttsPlayer.onerror = null;
            ttsPlayer.pause();
            ttsPlayer.currentTime = 0;
        } catch {}
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
        }
    }

    // ── SESSION RESET ──
    async function resetSession() {
        stopCall();
        try {
            await fetch('/api/reset-session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId })
            });
        } catch {}
        turnCount = 0;
        lastSummary = '';
        testDriveWelcomed = false;
        applyAssistantModeUI(true);
    }

    // ── MODAL LOGIC ──
    window.hmiOpenBooking = function(presetSummary) {
        openBookingModal(presetSummary);
    };

    function openBookingModal(summaryOverride) {
        bookingIssue.value = summaryOverride || lastSummary || "Vehicle Diagnostic Inspection";
        expertModalBackdrop.classList.add('active');
        bookingName.focus();
    }

    function closeBookingModal() { expertModalBackdrop.classList.remove('active'); }

    async function submitExpertBooking() {
        const name = bookingName.value.trim();
        const phone = bookingPhone.value.trim();
        const date = bookingDate.value;
        const time = bookingTime.value;
        const issue = bookingIssue.value.trim();

        if (!name || !phone) {
            alert('Please enter your name and contact phone number.');
            return;
        }

        const btnSubmit = document.getElementById('btn-submit-booking');
        btnSubmit.disabled = true;
        btnSubmit.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> CREATING BOOKING...`;

        try {
            const res = await fetch('/api/book-expert', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    customer_name: name,
                    customer_phone: phone,
                    preferred_date: date,
                    preferred_time: time,
                    issue_summary: issue,
                    language_code: selectedLanguage,
                    speaker: selectedSpeaker
                })
            });

            if (!res.ok) throw new Error('Booking API failed');
            const data = await res.json();

            closeBookingModal();
            renderBookingConfirmationCard(data);
        } catch (err) {
            console.error(err);
            alert('Failed to schedule expert call. Please check network connection.');
        } finally {
            btnSubmit.disabled = false;
            btnSubmit.innerHTML = `<i class="fa-solid fa-check"></i> <span>CONFIRM & GENERATE REF ID</span>`;
        }
    }

    function renderBookingConfirmationCard(data) {
        removeEmptyState();
        const bubble = document.createElement('div');
        bubble.className = 'bubble assistant';
        bubble.innerHTML = `
            <span class="who" style="color:var(--accent-green)">BOOKING CONFIRMATION &nbsp;·&nbsp; ${getTime()}</span>
            <div class="ai-report-card" style="border-left-color:var(--accent-green);">
                <div class="report-card-header">
                    <span style="font-family:var(--font-mono); color:var(--accent-green); font-weight:700;"><i class="fa-solid fa-circle-check"></i> SESSION BOOKED</span>
                    <span style="font-family:var(--font-mono); font-weight:700; color:var(--accent-amber);">${esc(data.reference_id)}</span>
                </div>
                <div style="font-size:0.82rem; line-height:1.5;">
                    <div><strong>Customer:</strong> ${esc(data.customer_name)} (${esc(data.customer_phone)})</div>
                    <div><strong>Assigned Expert:</strong> ${esc(data.assigned_expert)}</div>
                    <div><strong>Scheduled Slot:</strong> ${esc(data.scheduled_slot)}</div>
                </div>
                <div style="padding:0.5rem; background:rgba(0,230,118,0.08); border-radius:4px; font-size:0.8rem; color:var(--text-primary);">
                    ${esc(data.confirmation_message)}
                </div>
            </div>`;
        transcriptFeed.appendChild(bubble);
        scrollToBottom();

        if (data.audio_url || data.audio_b64) {
            playAudio(data.audio_b64, data.confirmation_message, null, data.audio_url);
        }
    }

    async function lookupBookingRef() {
        const ref = lookupRefInput.value.trim().toUpperCase();
        if (!ref) {
            alert('Please enter a Reference ID (e.g. TD-27821183 or REF-849204).');
            return;
        }

        btnSearchRef.disabled = true;
        btnSearchRef.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i>`;

        try {
            const isTestDrive = ref.startsWith('TD-');
            const endpoint = isTestDrive
                ? `/api/test-drive/bookings/${encodeURIComponent(ref)}`
                : `/api/booking/${encodeURIComponent(ref)}`;
            const res = await fetch(endpoint);
            if (!res.ok) throw new Error('Reference ID not found');
            const data = await res.json();

            lookupResultBox.className = 'lookup-result-box active';
            lookupResultBox.innerHTML = isTestDrive ? `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
                    <span style="font-family:var(--font-mono); color:var(--accent-blue); font-weight:700;">${esc(data.reference_id)}</span>
                    <span style="color:var(--accent-green); font-family:var(--font-mono); font-size:0.75rem;"><i class="fa-solid fa-circle-check"></i> ${esc(data.status)}</span>
                </div>
                <div style="font-family:var(--font-mono); font-size:0.78rem; color:var(--text-secondary); line-height:1.6;">
                    <div><strong>Customer:</strong> ${esc(data.customer_name)} (${esc(data.customer_mobile)})</div>
                    <div><strong>Car:</strong> ${esc(data.car_model)}</div>
                    <div><strong>Dealer:</strong> ${esc(data.dealership_name)}</div>
                    <div><strong>Date & time:</strong> ${esc(data.booking_date)} · ${esc(data.time_slot)}</div>
                    <div><strong>Location:</strong> ${esc(data.test_drive_address)}</div>
                    <div><strong>Documents to carry:</strong> Original driving licence + Aadhaar or PAN</div>
                    <div style="margin-top:0.3rem; color:var(--text-muted); font-size:0.68rem;">Created: ${esc(data.created_at)}</div>
                </div>` : `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
                    <span style="font-family:var(--font-mono); color:var(--accent-amber); font-weight:700;">${esc(data.reference_id)}</span>
                    <span style="color:var(--accent-green); font-family:var(--font-mono); font-size:0.75rem;"><i class="fa-solid fa-circle-check"></i> ${esc(data.status)}</span>
                </div>
                <div style="font-family:var(--font-mono); font-size:0.78rem; color:var(--text-secondary); line-height:1.6;">
                    <div><strong>Customer:</strong> ${esc(data.customer_name)} (${esc(data.customer_phone)})</div>
                    <div><strong>Assigned Expert:</strong> ${esc(data.assigned_expert)}</div>
                    <div><strong>Scheduled Slot:</strong> ${esc(data.scheduled_slot)}</div>
                    <div><strong>Issue:</strong> ${esc(data.issue_summary)}</div>
                    <div style="margin-top:0.3rem; color:var(--text-muted); font-size:0.68rem;">Created: ${esc(data.created_at)}</div>
                </div>`;
        } catch {
            lookupResultBox.className = 'lookup-result-box active';
            lookupResultBox.innerHTML = `
                <div style="color:var(--red-alert); font-family:var(--font-mono); font-size:0.75rem;">
                    <i class="fa-solid fa-triangle-exclamation"></i> Reference ID '${esc(ref)}' not found in active bookings database.
                </div>`;
        } finally {
            btnSearchRef.disabled = false;
            btnSearchRef.innerHTML = `<i class="fa-solid fa-magnifying-glass"></i> SEARCH`;
        }
    }

    // ── UTILS ──
    function bindQuickPromptButtons() {
        document.querySelectorAll('.symptom-preset').forEach(chip => {
            if (chip.dataset.bound === 'true') return;
            chip.dataset.bound = 'true';
            chip.addEventListener('click', () => {
                const prompt = chip.getAttribute('data-symptom');
                if (prompt) sendTextMessage(prompt);
            });
        });
    }

    function getTime() { return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
    function scrollToBottom() {
        requestAnimationFrame(() => {
            transcriptFeed.scrollTop = transcriptFeed.scrollHeight;
            setTimeout(() => { transcriptFeed.scrollTop = transcriptFeed.scrollHeight; }, 60);
        });
    }
    function esc(s) {
        return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }
});
