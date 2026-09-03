<template>
  <v-main class="editor-background" style="display:flex;flex-direction:column;height:100vh;overflow:hidden;">
    <v-app-bar app color="white" elevation="2" class="px-4" style="align-items:center;">
      <h1 class="text-h5 font-weight-bold app-bar-title" style="color:#1b263b;">Programming Assignment</h1>
 
      <!-- Timer alert inside app bar -->
      <v-spacer />
      <v-chip
        v-if="timeLeft <= 300 && timeLeft > 0"
        color="warning"
        text-color="white"
        variant="flat"
        size="small"
        class="mr-4"
      >
        ⏰ {{ formattedTime }} left
      </v-chip>
 
      <v-btn
        class="text-subtitle-2"
        color="#ff758f"
        size="small"
        variant="elevated"
        @click="logout"
      >
        Sign Out
      </v-btn>
    </v-app-bar>
 
    <!-- Main Content -->
    <div class="main-content-row">
      <!-- Error Alert -->
      <v-alert v-if="errorMessage" type="error" dismissible class="error-alert" @input="errorMessage = ''">
        {{ errorMessage }}
      </v-alert>
 
      <!-- Code Editor (Left Panel) -->
      <div class="editor-panel">
        <v-card elevation="3" class="rounded-card" style="flex:1;display:flex;flex-direction:column;overflow:hidden;">
          
          <!-- Question Section - SCROLLABLE -->
          <div class="question-section">
            <div class="question-content">
              <pre class="question-text">{{ question || 'Loading question…' }}</pre>
            </div>
          </div>
 
          <v-divider />
 
          <!-- File selector + Submit button -->
          <div class="language-section">
            <!-- File Selector (only shows for multi-file) -->
            <div v-if="isMultiFile" style="display:flex;align-items:center;gap:10px;">
              <span class="text-subtitle-2" style="font-weight:600;">Current File:</span>
              <v-select
                v-model="currentFileIndex"
                :items="fileSelectItems"
                density="compact"
                variant="outlined"
                hide-details
                style="max-width:200px;margin-left:12px;"
                @update:model-value="switchFile"
              >
                <template v-slot:selection="{ item }">
                  <v-icon size="small" class="mr-2">{{ getFileIcon(item.value) }}</v-icon>
                  <span>{{ item.title }}</span>
                </template>
                <template v-slot:item="{ item, props }">
                  <v-list-item v-bind="props">
                    <template v-slot:prepend>
                      <v-icon size="small">{{ getFileIcon(item.value) }}</v-icon>
                    </template>
                  </v-list-item>
                </template>
              </v-select>
              
              <!-- Read-only indicator for non-editable files -->
              <v-chip
                v-if="files[currentFileIndex] && !files[currentFileIndex].editable"
                size="small"
                color="warning"
                variant="outlined"
              >
                Read-only
              </v-chip>
            </div>
 
            <!-- Language indicator for single file -->
            <div v-else style="display:flex;align-items:center;gap:10px;">
              <v-icon class="mr-2">{{ language === 'python' ? 'mdi-language-python' : 'mdi-language-cpp' }}</v-icon>
              <span class="text-subtitle-2" style="font-weight:600;">Language: {{ language === 'python' ? 'Python' : 'C++' }}</span>
            </div>
 
            <!-- Right-aligned submit button -->
            <v-spacer></v-spacer>
 
            <v-btn
              color="primary"
              @click="handleSubmit"
              :loading="loading"
              :disabled="loading"
              size="small"
              elevation="2"
              prepend-icon="mdi-check-circle"
            >
              Submit Code
            </v-btn>
          </div>
 
          <v-divider />
 
          <!-- CodeMirror Editor - Takes remaining space -->
           <!-- CodeMirror Editor - Takes remaining space -->
          <div class="code-editor-container">
            <codemirror
              v-model="currentFileCode"
              :extensions="extensions"
              :placeholder="currentFilePlaceholder"
              :style="{ height: '100%', width: '100%' }"
              :autofocus="true"
              :indent-with-tab="true"
              :tab-size="2"
              :disabled="isCurrentFileReadonly"
              @ready="handleReady"
            />
          </div>
                
          <v-divider />
 
          <!-- Input Field & Run Button -->
          <div class="controls-section">
            <v-btn
              @click="handleRunCode"
              color="secondary"
              :loading="runLoading"
              :disabled="runLoading"
              size="large"
              prepend-icon="mdi-play"
            >
              Run Code
            </v-btn>
          </div>
 
          <!-- Output Section -->
          <v-expand-transition>
            <div v-if="runOutput" class="output-section">
              <div class="output-header">
                <v-icon color="white" size="small" class="mr-2">mdi-console</v-icon>
                <span style="font-weight:600;">Output:</span>
              </div>
              <pre class="output-content">{{ runOutput }}</pre>
            </div>
          </v-expand-transition>
        </v-card>
      </div>
 
      <!-- AI Assistant Chat (Right Panel) -->
      <div class="chat-panel">
        <v-card elevation="3" class="rounded-card" style="flex:1;display:flex;flex-direction:column;overflow:hidden;">
          <!-- Chat Header -->
          <div class="chat-header">
            <div style="display:flex;align-items:center;justify-content:space-between;">
              <div>
                <h2 class="text-h6 font-weight-bold">🤖 AI Learning Coach</h2>
              </div>
            </div>
          </div>
 
          <v-divider />
 
          <!-- Chat Messages Area - SCROLLABLE -->
          <div
            ref="chatMessages"
            class="chat-messages"
            @scroll="handleScroll"
          >
            <!-- Chat Messages -->
            <div v-for="(msg, index) in chatHistory" :key="index">
              <!-- Message Bubble -->
              <div :class="['chat-bubble', msg.role]">
                <div class="message-content">
                  <div class="message-header">
                    <span class="message-role">{{ msg.role === 'assistant' ? '🤖 AI Coach' : '👤 You' }}</span>
                    <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
                  </div>
                  <div class="message-text" v-html="formatMessage(msg.content)"></div>
                </div>
              </div>
 
              <!-- Thumbs Up/Down Feedback -->
              <div
                v-if="msg.role === 'assistant' && !msg.feedbackGiven && index === chatHistory.length - 1 && !aiLoading"
                class="feedback-section"
              >
                <span style="font-size:12px;color:#666;">Was this helpful?</span>
                <v-btn
                  icon
                  size="small"
                  variant="text"
                  color="success"
                  @click="handleThumbsFeedback(index, true)"
                >
                  <v-icon>mdi-thumb-up</v-icon>
                </v-btn>
                <v-btn
                  icon
                  size="small"
                  variant="text"
                  color="error"
                  @click="handleThumbsFeedback(index, false)"
                >
                  <v-icon>mdi-thumb-down</v-icon>
                </v-btn>
              </div>
 
              <!-- Feedback Given Indicator -->
              <div
                v-if="msg.role === 'assistant' && msg.feedbackGiven"
                class="feedback-given"
              >
                ✓ Thanks for the feedback!
              </div>
            </div>
 
            <!-- AI Typing Indicator -->
            <div v-if="aiLoading" class="chat-bubble assistant">
              <div class="message-content">
                <div class="typing-indicator">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            </div>
          </div>
 
          <v-divider />
 
          <!-- Chat Input Area -->
          <div class="chat-input-section">
            <v-textarea
              v-model="userMessage"
              placeholder="Ask for help with any step..."
              rows="3"
              auto-grow
              variant="outlined"
              density="compact"
              hide-details
              :disabled="aiLoading"
              @keydown.enter.exact.prevent="sendMessage"
              @keydown.shift.enter.prevent="userMessage += '\n'"
            />
            <div class="chat-input-footer">
              <div class="input-hint">
                <v-icon size="small" class="mr-1">mdi-information</v-icon>
                Press Enter to send, Shift+Enter for new line
              </div>
              <v-btn
                color="primary"
                @click="sendMessage"
                :loading="aiLoading"
                :disabled="aiLoading || !userMessage.trim()"
                prepend-icon="mdi-send"
              >
                Send
              </v-btn>
            </div>
          </div>
        </v-card>
      </div>
    </div>
  </v-main>
</template>
 
<script>
import api from "../axios";
import { Codemirror } from "vue-codemirror";
import { python } from "@codemirror/lang-python";
import { cpp } from "@codemirror/lang-cpp";
import { oneDark } from "@codemirror/theme-one-dark";
 
export default {
  name: "CodeEditorPage",
  components: { Codemirror },
  data() {
    return {
      // Multi-file support
      isMultiFile: false,
      files: [], // Array of {filename, code, editable}
      currentFileIndex: 0,
      language: "cpp", // overwritten once the question loads and reports its real language
      starterCpp: `#include <iostream>
using namespace std;

int main() {
    cout << "Hello, C++!" << endl;
    return 0;
}
`,
      starterPython: `def main():
    print("Hello, Python!")


if __name__ == "__main__":
    main()
`,

      questionId: this.$route.params.questionId,
      code: "",
      question: "",
      extensions: [cpp(), oneDark], // ✅ C++ only
      view: null,
      runOutput: "",
      runInput: "",
      loading: false,
      runLoading: false,
      timeLeft: 1800,
      timerInterval: null,
      autosaveInterval: null,
      errorMessage: "",
      errorTimeoutId: null,
      aiLoading: false,
      userMessage: "",
      chatHistory: [],
      currentPhase: "",
      currentStep: 0,
      totalSteps: 0,
      autoScrollEnabled: true,
    };
  },
  computed: {
    formattedTime() {
      const minutes = Math.floor(this.timeLeft / 60);
      const seconds = this.timeLeft % 60;
      return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
    },
    fileSelectItems() {
      if (!this.isMultiFile || this.files.length === 0) {
        return [];
      }
      return this.files.map((file, index) => ({
        title: file.filename,
        value: index
      }));
    },
    currentFileCode: {
      get() {
        if (this.isMultiFile && this.files[this.currentFileIndex]) {
          return this.files[this.currentFileIndex].code;
        }
        return this.code;
      },
      set(value) {
        if (this.isMultiFile && this.files[this.currentFileIndex]) {
          this.files[this.currentFileIndex].code = value;
        } else {
          this.code = value;
        }
      }
    },
    currentFilePlaceholder() {
      if (this.isMultiFile && this.files[this.currentFileIndex]) {
        const file = this.files[this.currentFileIndex];
        return file.editable ? `Write your ${file.filename} code here...` : 'This file is read-only';
      }
      return this.language === 'python' ? 'Write your Python code here...' : 'Write your C++ code here...';
    },
    isCurrentFileReadonly() {
      if (this.isMultiFile && this.files[this.currentFileIndex]) {
        return !this.files[this.currentFileIndex].editable;
      }
      return false;
    }
  },
  watch: {
    "$route.params.questionId"(newVal) {
      this.questionId = newVal;
      this.initializePage();
    },
    language() {
      this.updateExtensions();
    },
    errorMessage(newVal) {
      if (newVal) {
        if (this.errorTimeoutId) clearTimeout(this.errorTimeoutId);
        this.errorTimeoutId = setTimeout(() => {
          this.errorMessage = "";
          this.errorTimeoutId = null;
        }, 5000);
      }
    },
    chatHistory: {
      deep: true,
      handler() {
        if (this.autoScrollEnabled) {
          this.$nextTick(() => {
            this.scrollToBottom();
          });
        }
      }
    }
  },
  created() {
    this.initializePage();
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
      this.resetBasicState();
      this.fetchQuestion();
      this.fetchProgrammingData();
      this.loadExistingConversation();
      this.startTimers();
      this.updateExtensions();
    },
    resetBasicState() {
      this.question = "Loading question…";
      this.code = "";
      this.files = [];
      this.isMultiFile = false;
      this.currentFileIndex = 0;
      this.runInput = "";
      this.runOutput = "";
      this.userMessage = "";
      this.language = "cpp"; // placeholder until fetchProgrammingData reports the real one
    },
    startTimers() {
      clearInterval(this.timerInterval);
      clearInterval(this.autosaveInterval);
      this.timerInterval = setInterval(() => {
        if (this.timeLeft > 0) {
          this.timeLeft--;
        }
      }, 1000);
      this.autosaveInterval = setInterval(() => {
        this.autosaveCode();
      }, 30000);
    },
    updateExtensions() {
      this.extensions = this.language === 'python' ? [python(), oneDark] : [cpp(), oneDark];
    },
    getFileIcon(fileIndex) {
      if (!this.isMultiFile || !this.files[fileIndex]) return 'mdi-file-code';
      const filename = this.files[fileIndex].filename;
      if (filename.endsWith('.h')) return 'mdi-file-code';
      if (filename.endsWith('.cpp')) return 'mdi-language-cpp';
      if (filename.endsWith('.py')) return 'mdi-language-python';
      return 'mdi-file-code';
    },
    switchFile(newIndex) {
      this.currentFileIndex = newIndex;
    },
 
    fetchQuestion() {
      const token = this.getAccessToken();
      api.get(`/question/${this.questionId}`, {
        headers: { Authorization: `Bearer ${token}` }
      })
        .then((res) => {
          if (res.data.status === "success") {
            this.question = res.data.question.question_text || "No question text available.";
          }
        })
        .catch((err) => {
          console.error("Error fetching question:", err);
          this.question = "Error loading question.";
        });
    },
    fetchProgrammingData() {
      const token = this.getAccessToken();
      api.get(`/programming/${this.questionId}`, {
        headers: { Authorization: `Bearer ${token}` }
      })
        .then((res) => {
          if (res.data.status === "success") {
            const questionData = res.data.question;
            
            // Check if multi-file question (multi-file is a C++-only feature here --
            // header/source splitting doesn't apply to Python questions)
            if (questionData.file_structure && questionData.file_structure.type === 'multi-file') {
              this.isMultiFile = true;
              this.language = 'cpp';
              this.files = questionData.file_structure.files.map(file => ({
                filename: file.filename,
                code: file.code || '',
                editable: file.editable !== false
              }));
              this.currentFileIndex = 0;
            } else {
              // Single file mode -- language comes from the question itself
              this.isMultiFile = false;
              this.language = (questionData.language || 'cpp').toLowerCase();
              const starter = this.language === 'python' ? this.starterPython : this.starterCpp;
              const saved = res.data.code;
              this.code = saved && saved.trim().length > 0 ? saved : starter;
            }
            
            const durationMinutes = res.data.timer_duration || 30;
            this.timeLeft = durationMinutes * 60;
            this.updateExtensions();
          }
        })
        .catch((err) => {
          console.error("Error fetching programming data:", err);
        });
    },
    loadExistingConversation() {
      const token = this.getAccessToken();
      api.get(`/programming/${this.questionId}/conversation_state`, {
        headers: { Authorization: `Bearer ${token}` }
      })
        .then((res) => {
          if (res.data.status === "success") {
            const history = res.data.conversation_history || [];
            
            if (history.length > 0) {
              this.chatHistory = history.map(msg => ({
                role: msg.role === 'user' ? 'user' : 'assistant',
                content: msg.content,
                timestamp: new Date(),
                feedbackGiven: false
              }));
              
              this.currentPhase = res.data.phase || 'PLANNING';
              this.currentStep = res.data.step_info?.current || 0;
              this.totalSteps = res.data.step_info?.total || 0;
            } else {
              this.startAIConversation();
            }
          } else {
            this.startAIConversation();
          }
        })
        .catch(err => {
          console.error("Error loading conversation:", err);
          this.startAIConversation();
        });
    },
    autosaveCode() {
      const token = this.getAccessToken();
      if (!token) return;
 
      if (this.isMultiFile) {
        // Save all files
        const filesToSave = this.files.filter(f => f.code && f.code.trim());
        if (filesToSave.length === 0) return;
 
        api.post(
          `/programming/${this.questionId}/autosave`,
          { files: filesToSave },
          { headers: { Authorization: `Bearer ${token}` } }
        ).catch((err) => {
          console.error("Autosave error:", err);
        });
      } else {
        // Single file save
        if (!this.code || !this.code.trim()) return;
        
        api.post(
          `/programming/${this.questionId}/autosave`,
          { code: this.code, language: this.language },
          { headers: { Authorization: `Bearer ${token}` } }
        ).catch((err) => {
          console.error("Autosave error:", err);
        });
      }
    },
    handleRunCode() {
      if (this.runLoading) return;
      this.runLoading = true;
      this.runOutput = "";
      const token = this.getAccessToken();
 
      const payload = this.isMultiFile
        ? { files: this.files, input: this.runInput }
        : { code: this.code, language: this.language, input: this.runInput };
 
      api.post(
        `/programming/${this.questionId}/run`,
        payload,
        { headers: { Authorization: `Bearer ${token}` } }
      )
        .then((res) => {
          if (res.data && res.data.status === "success") {
            this.runOutput = res.data.output || "(no output)";
          } else {
            let output = "";
            if (res.data?.stdout) output += res.data.stdout;
            if (res.data?.stderr) output += (output ? "\n" : "") + res.data.stderr;
            this.runOutput = output || res.data?.message || "(no output)";
          }
        })
        .catch((err) => {
          console.error("Run error:", err);
          this.runOutput = err.response?.data?.message || "Error running code.";
        })
        .finally(() => {
          this.runLoading = false;
        });
    },
    
    // ✅ UPDATED handleSubmit - Dynamic navigation based on backend response
    async handleSubmit() {
      if (this.loading) return;
      this.errorMessage = "";
      this.loading = true;
      const token = this.getAccessToken();
 
      const payload = this.isMultiFile
        ? { files: this.files }
        : { code: this.code, language: this.language };
 
      try {
        const response = await api.post(
          `/programming/${this.questionId}/submit`,
          payload,
          { headers: { Authorization: `Bearer ${token}` } }
        );
 
        if (response.data.status === 'success') {
          // ✅ Dynamic navigation based on backend response
          const nextAction = response.data.next_action;
          
          if (nextAction === 'next_question') {
            // Navigate to next question
            const nextQuestionId = response.data.next_question_id;
            this.$router.replace({
              name: "Editor",
              params: { questionId: nextQuestionId }
            });
          } else if (nextAction === 'postsurvey') {
            // Go to post survey
            this.$router.replace({ name: "PostSurvey" });
          } else {
            // Fallback: go to completion
            this.$router.replace({ name: "Completion" });
          }
        }
      } catch (error) {
        console.error("Submit error:", error);
        this.errorMessage = error?.response?.data?.message || "Submit failed.";
      } finally {
        this.loading = false;
      }
    },
 
    async startAIConversation() {
      this.aiLoading = true;
      const token = this.getAccessToken();
      
      const currentCode = this.isMultiFile
        ? this.files.map(f => `// ${f.filename}\n${f.code}`).join('\n\n')
        : this.code;
 
      try {
        const response = await api.post(
          `/programming/${this.questionId}/prompt`,
          {
            prompt: "Start with a warm greeting and break down the problem into clear steps.",
            code: currentCode,
            terminal_output: this.runOutput,
            action: 'start',
            hide_user_prompt: true
          },
          { headers: { Authorization: `Bearer ${token}` } }
        );
        const aiMessage = response.data.ai_response;
        this.currentPhase = response.data.phase || 'PLANNING';
        this.currentStep = response.data.step_info?.current || 0;
        this.totalSteps = response.data.step_info?.total || 3;
        this.chatHistory.push({
          role: 'assistant',
          content: aiMessage,
          timestamp: new Date(),
          feedbackGiven: false
        });
      } catch (error) {
        console.error("Error starting conversation:", error);
        this.currentPhase = 'PLANNING';
      } finally {
        this.aiLoading = false;
      }
    },
    
    async sendMessage() {
      if (!this.userMessage.trim() || this.aiLoading) return;
      const userMsg = this.userMessage.trim();
      this.userMessage = "";
      this.chatHistory.push({
        role: 'user',
        content: userMsg,
        timestamp: new Date()
      });
      this.aiLoading = true;
      const token = this.getAccessToken();
 
      const currentCode = this.isMultiFile
        ? this.files.map(f => `// ${f.filename}\n${f.code}`).join('\n\n')
        : this.code;
 
      try {
        const response = await api.post(
          `/programming/${this.questionId}/prompt`,
          {
            prompt: userMsg,
            code: currentCode,
            terminal_output: this.runOutput,
            action: 'continue'
          },
          { headers: { Authorization: `Bearer ${token}` } }
        );
        const aiMessage = response.data.ai_response;
        this.currentPhase = response.data.phase || this.currentPhase;
        this.currentStep = response.data.step_info?.current || this.currentStep;
        this.totalSteps = response.data.step_info?.total || this.totalSteps;
        this.chatHistory.push({
          role: 'assistant',
          content: aiMessage,
          timestamp: new Date(),
          feedbackGiven: false
        });
      } catch (error) {
        console.error("Error sending message:", error);
        this.chatHistory.push({
          role: 'assistant',
          content: "I'm sorry, I'm having trouble responding right now. Please try again.",
          timestamp: new Date(),
          feedbackGiven: false
        });
      } finally {
        this.aiLoading = false;
      }
    },
    
    async handleThumbsFeedback(messageIndex, isHelpful) {
      this.chatHistory[messageIndex].feedbackGiven = true;
      this.chatHistory[messageIndex].feedback = isHelpful;
      const token = this.getAccessToken();
      try {
        await api.post(
          `/programming/${this.questionId}/feedback`,
          {
            helpful: isHelpful,
            phase: this.currentPhase,
            message_index: messageIndex,
            message_content: this.chatHistory[messageIndex].content
          },
          { headers: { Authorization: `Bearer ${token}` } }
        );
      } catch (error) {
        console.error("Error logging feedback:", error);
      }
      if (!isHelpful) {
        setTimeout(() => {
          this.chatHistory.push({
            role: 'assistant',
            content: "I'm sorry that wasn't helpful. What specifically would you like me to explain differently?",
            timestamp: new Date(),
            feedbackGiven: false
          });
        }, 500);
      }
    },
    
    formatMessage(content) {
      if (!content) return '';
      let formatted = content.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
        return `<pre class="code-example"><code>${this.escapeHtml(code.trim())}</code></pre>`;
      });
      formatted = formatted.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
      formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
      formatted = formatted.replace(/\n/g, '<br>');
      return formatted;
    },
    
    escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    },
    
    scrollToBottom() {
      if (this.$refs.chatMessages) {
        this.$refs.chatMessages.scrollTop = this.$refs.chatMessages.scrollHeight;
      }
    },
    
    handleScroll() {
      const container = this.$refs.chatMessages;
      if (container) {
        const isAtBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 50;
        this.autoScrollEnabled = isAtBottom;
      }
    },
    
    formatTime(timestamp) {
      if (!timestamp) return '';
      const date = new Date(timestamp);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
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
    }
  }
};
</script>
 
<style scoped>
.editor-background {
  background-color: #f5f7fa;
}

/* ========== MAIN LAYOUT (editor + AI chat panels) ========== */
.main-content-row {
  flex: 1;
  display: flex;
  overflow: hidden;
  padding: 16px;
  gap: 16px;
}

.editor-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-panel {
  width: 520px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* Below this width there isn't room for editor + a 520px chat panel side by
   side without squeezing the editor unusably narrow -- stack them instead. */
@media (max-width: 900px) {
  .main-content-row {
    flex-direction: column;
    overflow-y: auto;
    padding: 12px;
    gap: 12px;
  }

  .editor-panel {
    flex: 1 1 55vh;
    min-height: 320px;
  }

  .chat-panel {
    width: 100%;
    flex: 1 1 55vh;
    min-height: 320px;
  }
}

@media (max-width: 480px) {
  .main-content-row {
    padding: 8px;
    gap: 8px;
  }

  .app-bar-title {
    font-size: 1.1rem !important;
  }
}
 
.rounded-card {
  border-radius: 12px;
}
 
/* ========== TIMER ALERT (Only last 5 minutes) ========== */
.timer-alert {
  position: fixed;
  top: 70px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 999;
  max-width: 600px;
  animation: pulse 2s infinite;
}
 
@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.8;
  }
}
 
/* ========== QUESTION SECTION (SCROLLABLE) ========== */
.question-section {
  flex: 0 0 auto;
  max-height: 200px;
  display: flex;
  flex-direction: column;
  background-color: #fafbfc;
}
 
.question-header {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  background-color: #e3f2fd;
  border-bottom: 1px solid #bbdefb;
}
 
.question-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
 
.question-text {
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  font-size: 14px;
  line-height: 1.6;
  color: #333;
  margin: 0;
}
 
.question-content::-webkit-scrollbar {
  width: 8px;
}
 
.question-content::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}
 
.question-content::-webkit-scrollbar-thumb {
  background: #90caf9;
  border-radius: 4px;
}
 
.question-content::-webkit-scrollbar-thumb:hover {
  background: #64b5f6;
}
 
/* ========== LANGUAGE SECTION ========== */
.language-section {
  padding: 10px 16px;
  display: flex;
  align-items: center;
  background-color: #fff;
}
 
/* ========== CODE EDITOR ========== */
.code-editor-container {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background-color: #1e1e1e;
}
 
/* ========== CONTROLS SECTION ========== */
.controls-section {
  padding: 12px 16px;
  display: flex;
  gap: 12px;
  align-items: center;
  background-color: #fff;
}
 
/* ========== OUTPUT SECTION ========== */
.output-section {
  max-height: 200px;
  overflow-y: auto;
  background-color: #1e1e1e;
  color: #d4d4d4;
  border-top: 2px solid #333;
}
 
.output-header {
  padding: 8px 16px;
  background-color: #2d2d2d;
  color: white;
  display: flex;
  align-items: center;
  font-size: 13px;
  border-bottom: 1px solid #444;
}
 
.output-content {
  padding: 16px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  white-space: pre-wrap;
  margin: 0;
  line-height: 1.5;
}
 
.output-section::-webkit-scrollbar {
  width: 8px;
}
 
.output-section::-webkit-scrollbar-track {
  background: #2d2d2d;
}
 
.output-section::-webkit-scrollbar-thumb {
  background: #555;
  border-radius: 4px;
}
 
/* ========== CHAT HEADER ========== */
.chat-header {
  padding: 16px;
  background-color: #fff;
}
 
.step-indicator {
  font-size: 12px;
  color: #666;
  margin-top: 4px;
}
 
/* ========== CHAT MESSAGES (SCROLLABLE) ========== */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  background-color: #f5f5f5;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  scroll-behavior: smooth;
  min-height: 0;
}
 
.chat-messages::-webkit-scrollbar {
  width: 6px;
}
 
.chat-messages::-webkit-scrollbar-track {
  background: #e0e0e0;
}
 
.chat-messages::-webkit-scrollbar-thumb {
  background: #bdbdbd;
  border-radius: 3px;
}
 
.chat-messages::-webkit-scrollbar-thumb:hover {
  background: #9e9e9e;
}
 
.chat-bubble {
  display: flex;
  animation: slideIn 0.3s ease-out;
}
 
@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
 
.chat-bubble.assistant {
  justify-content: flex-start;
}
 
.chat-bubble.user {
  justify-content: flex-end;
}
 
.message-content {
  max-width: 85%;
  padding: 12px 16px;
  border-radius: 12px;
  background-color: white;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
 
.chat-bubble.assistant .message-content {
  background-color: #e3f2fd;
  border-bottom-left-radius: 4px;
}
 
.chat-bubble.user .message-content {
  background-color: #c8e6c9;
  border-bottom-right-radius: 4px;
}
 
.message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  font-size: 11px;
  color: #666;
}
 
.message-role {
  font-weight: 600;
  font-size: 12px;
}
 
.message-time {
  font-size: 10px;
  color: #999;
}
 
.message-text {
  word-wrap: break-word;
  line-height: 1.6;
  color: #333;
  font-size: 14px;
}
 
/* ========== CODE FORMATTING IN MESSAGES ========== */
.message-text >>> .code-example {
  background-color: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  margin: 8px 0;
  line-height: 1.5;
}
 
.message-text >>> .inline-code {
  background-color: #f5f5f5;
  color: #c7254e;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
}
 
.chat-bubble.assistant .message-text >>> .inline-code {
  background-color: #bbdefb;
  color: #0d47a1;
}
 
.message-text >>> strong {
  font-weight: 600;
  color: #1976d2;
}
 
/* ========== FEEDBACK SECTION ========== */
.feedback-section {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  margin-bottom: 8px;
  padding-left: 12px;
  animation: fadeIn 0.3s ease-in;
}
 
@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
 
.feedback-given {
  text-align: left;
  font-size: 11px;
  color: #999;
  margin-top: 4px;
  margin-bottom: 8px;
  padding-left: 12px;
}
 
/* ========== TYPING INDICATOR ========== */
.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 8px 0;
}
 
.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #90caf9;
  animation: typing 1.4s infinite;
}
 
.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}
 
.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}
 
@keyframes typing {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.5;
  }
  30% {
    transform: translateY(-10px);
    opacity: 1;
  }
}
 
/* ========== CHAT INPUT SECTION ========== */
.chat-input-section {
  padding: 16px;
  background-color: white;
  border-top: 1px solid #e0e0e0;
}
 
.chat-input-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}
 
.input-hint {
  font-size: 11px;
  color: #999;
  display: flex;
  align-items: center;
}
 
/* ========== ERROR ALERT ========== */
.error-alert {
  position: fixed;
  top: 80px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  max-width: 600px;
  animation: slideDown 0.3s ease-out;
}
 
@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
}
 
/* ========== RESPONSIVE DESIGN ========== */
@media (max-width: 960px) {
  .question-section {
    max-height: 150px;
  }
}
 
@media (max-width: 600px) {
  .chat-input-footer {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }
  
  .input-hint {
    justify-content: center;
  }
  
  .message-content {
    max-width: 90%;
  }
}
</style>
 