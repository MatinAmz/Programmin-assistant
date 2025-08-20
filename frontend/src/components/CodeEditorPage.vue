<template>
  <v-main class="editor-background" style="display:flex;flex-direction:column;height:100vh;">
    <!-- App Bar -->
    <v-app-bar app color="white" elevation="2" class="px-4">
      <h1 class="text-h5 font-weight-bold" style="color:#1b263b;">Code Editor</h1>
      <v-spacer />
      <v-btn class="text-subtitle-2" color="#ff758f" size="small" variant="elevated" @click="logout">
        Sign Out
      </v-btn>
    </v-app-bar>

    <!-- Main Content -->
    <div style="flex:1;display:flex;flex-direction:column;overflow-y:auto;padding:8px;padding-bottom:60px;">
      <!-- Error Alert -->
      <v-alert v-if="errorMessage" type="error" dismissible class="error-alert" @input="errorMessage = ''">
        {{ errorMessage }}
      </v-alert>

      <v-row no-gutters wrap style="flex:1;">
        <!-- Code Editor -->
        <v-col xs="12" md="8" class="pa-2">
          <v-card elevation="8" class="pa-4 rounded-card" style="display:flex;flex-direction:column;height:100%;">
            <!-- Question -->
            <div class="pa-6" style="flex:0 0 auto;white-space:pre-wrap;overflow-wrap:break-word;margin-bottom:8px;">
              {{ question || 'Loading question…' }}
            </div>

            <!-- Timer -->
            <div style="flex:0 0 auto;">
              <div style="text-align:left;margin-bottom:8px;">
                <span :style="{ color: timeLeft < 300 ? 'red' : 'black', fontWeight: 'bold' }">
                  Remaining time: {{ formattedTime }}
                </span>
              </div>
            </div>

            <!-- CodeMirror -->
            <div style="flex:1;border:1px solid #ccc;border-radius:4px;padding:8px;overflow-y:auto;">
              <codemirror
                v-model="code"
                :extensions="extensions"
                placeholder="Code goes here..."
                :style="{ height: '100%' }"
                :autofocus="true"
                :indent-with-tab="true"
                :tab-size="2"
                @ready="handleReady"
              />
            </div>

            <!-- Run Code -->
            <div style="flex:0 0 auto;margin-top:8px;display:flex;align-items:center;justify-content:center;">
              <v-btn class="text-subtitle-1" @click="handleRunCode" color="secondary" :loading="runLoading" :disabled="runLoading">
                Run Code
              </v-btn>
            </div>

            <!-- Output -->
            <v-expand-transition>
              <div v-if="runOutput" class="mt-4 pa-4 output-box rounded-card">
                <div style="font-weight:bold;margin-bottom:4px;">Output:</div>
                <div style="white-space:pre-wrap;">{{ runOutput }}</div>
              </div>
            </v-expand-transition>
          </v-card>
        </v-col>

        <!-- Right Panel: AI Assistant -->
        <v-col xs="12" md="4" class="pa-2">
          <v-card elevation="8" class="pa-4 rounded-card" style="display:flex;flex-direction:column;height:100%;">
            <div style="flex:0 0 auto;height:60px;display:flex;align-items:center;justify-content:center;">
              <h1 class="text-h5 font-weight-bold" style="margin:0;">AI-Assistant</h1>
            </div>

            <!-- AI Response box -->
            <div class="srl-output" style="flex:1;border:1px solid #ccc;border-radius:4px;background-color:#2E2E2E;color:white;padding:8px;overflow-y:auto;">
              <div v-if="aiResponse">
                {{ aiResponse }}
              </div>
              <div v-else>
                <template v-if="aiMode === 'srl'">
                  Click a phase button below to open options and select one for guidance!
                </template>
                <template v-else-if="aiMode === 'free'">
                  Type your prompt below and press Send (or Ctrl+Enter).
                </template>
                <template v-else>
                  Loading assistant…
                </template>
              </div>
            </div>

            <!-- Mode-specific controls -->
            <div style="flex:0 0 auto;margin-top:8px;">
              <!-- Experiment group: SRL buttons -->
              <div
                v-if="aiMode === 'srl'"
                style="display:flex;flex-direction:row;gap:8px;justify-content:space-around;"
              >
                <v-btn color="primary" @click="openPhaseDialog('Planning')"   :loading="srlLoading" :disabled="srlLoading">Planning</v-btn>
                <v-btn color="primary" @click="openPhaseDialog('Monitoring')" :loading="srlLoading" :disabled="srlLoading">Monitoring</v-btn>
                <v-btn color="primary" @click="openPhaseDialog('Reflection')" :loading="srlLoading" :disabled="srlLoading">Reflection</v-btn>
              </div>

              <!-- Control group: free prompt -->
              <div v-else-if="aiMode === 'free'">
                <v-textarea
                  v-model="freePrompt"
                  label="Write your prompt"
                  auto-grow
                  rows="2"
                  variant="outlined"
                  :disabled="srlLoading"
                  @keydown.ctrl.enter.prevent="handleFreePromptSend"
                />
                <div style="display:flex;justify-content:flex-end;margin-top:6px;">
                  <v-btn color="primary" :loading="srlLoading" :disabled="srlLoading || !freePrompt.trim()" @click="handleFreePromptSend">
                    Send
                  </v-btn>
                </div>
              </div>
            </div>
          </v-card>
        </v-col>
      </v-row>
    </div>

    <!-- Submit Button -->
    <div style="position:fixed;bottom:12px;left:50%;transform:translateX(-50%);z-index:10;">
      <v-btn class="text-subtitle-1" @click="handleSubmit" color="primary" :loading="loading" :disabled="loading">
        Submit Code
      </v-btn>
    </div>

    <!-- SRL Options Dialog -->
    <v-dialog v-model="showDialog" max-width="400">
      <v-card>
        <v-card-title>{{ selectedPhase }} Options</v-card-title>
        <v-card-text>
          <v-virtual-scroll :items="currentPhaseItems" height="300" item-height="48">
            <template #default="{ item }">
              <v-list-item :active="selectedItem === item.label" @click="handleSRLButtonClick(item)" class="srl-list-item">
                <v-list-item-title>{{ item.label }}</v-list-item-title>
              </v-list-item>
            </template>
          </v-virtual-scroll>
        </v-card-text>
        <v-card-actions>
          <v-btn color="primary" text @click="showDialog = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-main>
</template>

<script>
import api from "../axios";
import { Codemirror } from "vue-codemirror";
import { python } from "@codemirror/lang-python";
import { oneDark } from "@codemirror/theme-one-dark";

export default {
  name: "CodeEditorPage",
  components: { Codemirror },
  data() {
    return {
      // NEW: mode + free prompt
      aiMode: null,     // 'srl' (experiment) or 'free' (control)
      freePrompt: "",   // control input

      questionId: this.$route.params.questionId,
      code: "# Write your Python code here\n",
      question: "",
      extensions: [python(), oneDark],
      view: null,
      runOutput: "",
      loading: false,
      runLoading: false,
      srlLoading: false,
      timeLeft: 600,
      timerInterval: null,
      autosaveInterval: null,
      errorMessage: "",
      errorTimeoutId: null,
      aiResponse: "",
      selectedItem: "",
      showDialog: false,
      selectedPhase: "",
      currentPhaseItems: [],
      srlPhases: {
        Planning: [
          { label: "Help me plan", prompt: "Can you help me break down this problem into steps?" },
          { label: "Clarify the goal", prompt: "Can you help me restate the problem simply?" },
          { label: "Set sub-goals", prompt: "What smaller goals can I set for this coding task?" },
          { label: "Prioritize steps", prompt: "How should I prioritize these steps in my plan?" },
          { label: "Anticipate challenges", prompt: "What potential issues might I face, and how to prepare?" },
        ],
        Monitoring: [
          { label: "Check my approach", prompt: "Does this approach make sense? Here's my idea." },
          { label: "I feel stuck", prompt: "What should I try next?" },
          { label: "Track progress", prompt: "Am I on track with my plan? Update me on my progress." },
          { label: "Verify code", prompt: "Does this code snippet work as expected? Test it." },
          { label: "Manage frustration", prompt: "I'm feeling frustrated with this error—suggest a mindset shift or break." },
        ],
        Reflection: [
          { label: "Help me reflect", prompt: "What did I do and what did I learn?" },
          { label: "What could I improve?", prompt: "How can I improve or optimize my solution?" },
          { label: "Evaluate efficiency", prompt: "Was my solution efficient? How can it be optimized?" },
          { label: "Attribute success", prompt: "Why did this work (or not)? What strategies helped?" },
          { label: "Plan for next time", prompt: "What will I do differently in similar tasks without AI?" },
        ]
      },
    };
  },
  computed: {
    formattedTime() {
      const minutes = Math.floor(this.timeLeft / 60);
      const seconds = this.timeLeft % 60;
      return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
    },
  },
  created() {
    this.initializePage();
  },
  watch: {
    "$route.params.questionId"(newVal) {
      this.questionId = newVal;
      this.initializePage();
    },
    errorMessage(newVal) {
      if (newVal) {
        if (this.errorTimeoutId) clearTimeout(this.errorTimeoutId);
        this.errorTimeoutId = setTimeout(() => {
          this.errorMessage = "";
          this.errorTimeoutId = null;
        }, 3000);
      } else if (this.errorTimeoutId) {
        clearTimeout(this.errorTimeoutId);
        this.errorTimeoutId = null;
      }
    },
  },
  beforeUnmount() {
    clearInterval(this.timerInterval);
    clearInterval(this.autosaveInterval);
    if (this.errorTimeoutId) clearTimeout(this.errorTimeoutId);
  },
  methods: {
    initializePage() {
      const token = this.getAccessToken();
      if (!token) {
        this.$router.push({ name: "Login" });
        return;
      }
      this.fetchQuestion();
      this.fetchProgrammingData();

      clearInterval(this.timerInterval);
      clearInterval(this.autosaveInterval);

      this.timerInterval = setInterval(() => {
        if (this.timeLeft > 0) {
          this.timeLeft--;
          if (this.timeLeft === 0) {
            clearInterval(this.timerInterval);
            this.handleSubmit();
          }
        }
      }, 1000);

      this.autosaveInterval = setInterval(() => {
        this.autosaveCode();
      }, 30000);
    },
    fetchQuestion() {
      const token = this.getAccessToken();
      api.get(`/question/${this.questionId}`, { headers: { Authorization: `Bearer ${token}` } })
        .then((res) => {
          if (res.data.status === "success") {
            this.question = res.data.question.question_text || "No question text available.";
          } else {
            console.error(res.data.message);
            this.question = "Error loading question.";
          }
        })
        .catch((err) => {
          console.error(err);
          this.question = "Error loading question.";
        });
    },
    fetchProgrammingData() {
      const token = this.getAccessToken();
      api.get(`/programming/${this.questionId}`, { headers: { Authorization: `Bearer ${token}` } })
        .then((res) => {
          if (res.data.status === "success") {
            this.code = res.data.code || "# No starter code";
            const durationMinutes = res.data.timer_duration || 30;
            this.timeLeft = durationMinutes * 60;

            // NEW: capture mode from backend: 'free' (control) or 'srl' (experiment)
            this.aiMode = res.data.ai_mode || "srl";
          } else {
            console.error(res.data.message);
          }
        })
        .catch((err) => console.error(err));
    },
    logout() {
      document.cookie = "access_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
      this.$router.replace({ name: "Login" });
    },
    getAccessToken() {
      const value = `; ${document.cookie}`;
      const parts = value.split(`; access_token=`);
      if (parts.length === 2) return parts.pop().split(";").shift();
      return null;
    },
    handleReady(payload) {
      this.view = payload.view;
    },
    handleSubmit() {
      if (this.loading) return;
      this.errorMessage = "";
      this.loading = true;
      const token = this.getAccessToken();
      api.post(
        `/programming/${this.questionId}/submit`,
        { code: this.code },
        { headers: { Authorization: `Bearer ${token}` } }
      )
      .then((response) => {
        const message = response.data.message || "";
        if (message.includes("programming question 2") && this.questionId !== "2") {
          this.$router.replace({ name: "Editor", params: { questionId: "2" } });
        } else if (this.questionId === "2") {
          this.$router.replace({ name: "PostSurvey" });
        } else {
          this.$router.replace({ name: "Completion" });
        }
      })
      .catch((error) => {
        if (error.response && error.response.status === 400 && error.response.data && error.response.data.message) {
          this.errorMessage = error.response.data.message;
        } else {
          console.error(error);
        }
      })
      .finally(() => {
        this.loading = false;
      });
    },
    handleRunCode() {
      if (this.runLoading) return;
      this.runLoading = true;
      this.runOutput = "";
      const token = this.getAccessToken();
      api.post(`/run_code_raw`, { code: this.code }, { headers: { Authorization: `Bearer ${token}` } })
        .then((res) => {
          let output = "";
          if (res.data.stdout) output += res.data.stdout;
          if (res.data.stderr) output += (output ? "\n" : "") + res.data.stderr;
          this.runOutput = output || "(no output)";
        })
        .catch((err) => {
          console.error(err);
          this.runOutput = "Error running code.";
        })
        .finally(() => {
          this.runLoading = false;
        });
    },
    autosaveCode() {
      const token = this.getAccessToken();
      if (!token) return;
      api.post(
        `/programming/${this.questionId}/autosave`,
        { code: this.code },
        { headers: { Authorization: `Bearer ${token}` } }
      ).then((res) => {
        console.log("Code auto-saved:", res.data.message);
      }).catch((err) => console.error("Autosave error:", err));
    },

    // ---------- SRL (experiment) ----------
    openPhaseDialog(phase) {
      this.selectedPhase = phase;
      this.currentPhaseItems = this.srlPhases[phase];
      this.showDialog = true;
      this.selectedItem = "";
    },
    handleSRLButtonClick(item) {
      if (this.srlLoading) return;
      this.srlLoading = true;
      this.aiResponse = "";
      this.selectedItem = item.label;

      const fullPrompt = `
        ${item.prompt}
        Programming task: ${this.question || 'No question loaded'}
        Current code: ${this.code}
        Latest terminal output: ${this.runOutput || 'No recent output'}
      `;

      const token = this.getAccessToken();
      api.post(
        `/programming/${this.questionId}/prompt`,
        { prompt: fullPrompt, code: this.code },
        { headers: { Authorization: `Bearer ${token}` } }
      )
      .then((res) => {
        this.aiResponse = (res.data.ai_response || "No response from AI.").trim();
      })
      .catch((err) => {
        console.error(err);
        this.aiResponse = "Error getting AI response.";
      })
      .finally(() => {
        this.srlLoading = false;
        this.showDialog = false;
      });
    },

    // ---------- Free prompt (control) ----------
    handleFreePromptSend() {
      if (this.srlLoading || !this.freePrompt.trim()) return;
      this.srlLoading = true;
      this.aiResponse = "";
      const token = this.getAccessToken();

      const fullPrompt = `
        ${this.freePrompt}
        Programming task: ${this.question || 'No question loaded'}
        Current code: ${this.code}
        Latest terminal output: ${this.runOutput || 'No recent output'}
      `;

      api.post(
        `/programming/${this.questionId}/prompt`,
        { prompt: fullPrompt, code: this.code },
        { headers: { Authorization: `Bearer ${token}` } }
      )
      .then((res) => {
        this.aiResponse = (res.data.ai_response || "No response from AI.").trim();
        this.freePrompt = "";
      })
      .catch((err) => {
        console.error(err);
        this.aiResponse = err?.response?.data?.message || "Error getting AI response.";
      })
      .finally(() => {
        this.srlLoading = false;
      });
    },
  },
};
</script>

<style scoped>
.editor-background { background-color: #dee2e6; }
.timer { font-size: 1rem; font-weight: bold; color: #0d1b2a; }
.output-box { background-color: #2E2E2E; color: white; }
.rounded-card { border-radius: 12px; }
.srl-output { white-space: pre-wrap; }
.srl-list-item { cursor: pointer; }
.srl-list-item.active { background-color:#e3f2fd; color:#1976d2; }
.error-alert {
  position: fixed; top: 10px; left: 50%; transform: translateX(-50%);
  z-index: 9999; display: inline-flex !important;
}
.error-alert .v-alert__dismissible {
  order: -1 !important; top: auto !important; right: auto !important;
  transform: none !important; margin-right: 8px !important; margin-left: 0 !important;
}
</style>
