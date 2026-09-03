<template>
  <v-main class="editor-background">
    <v-container fluid class="pa-0" style="height: 100vh; padding: 8px;">
      <!-- Header Section -->
      <v-app-bar app color="white" elevation="2" class="px-4">
        <h1 class="text-h5 font-weight-bold" style="color: #1b263b;">Pre Survey</h1>
        <v-spacer></v-spacer>
        <v-btn class="text-subtitle-2"
          color="#ef233c"
          size="small"
          variant="flat"
          @click="logout">
          Sign Out
        </v-btn>
      </v-app-bar>
      <div class="ma-4 d-flex flex-column" style="height: 100%;">
        <!-- Question Card -->
        <div style="flex: 0 0 auto;">
          <v-card elevation="8" class="pa-6 rounded-card" style="width: 100%;">
            <h1 class="text-h6">Question 1</h1>
            <p class="text-body-1">
              {{ question || 'Loading question...' }}
            </p>
          </v-card>
        </div>

        <!-- Main Content Area -->
        <div style="flex: 1 1 auto; margin-top: 8px; margin-bottom: 8px;">
          <v-row no-gutters style="height: 100%;">
            <!-- Code Editor Column -->
            <v-col cols="12" md="8" style="padding: 4px;">
              <v-card elevation="8" class="pa-4 rounded-card"
                style="width: 100%; height: calc(100vh - 230px); display: flex; flex-direction: column;">
                <div style="height: 60px;">
                  <h1 class="text-h5 text-center" style="margin: 0; padding-bottom: 8px;">Code Editor</h1>
                </div>
                <div style="height: calc(100% - 110px); overflow-y: auto; border: 1px solid #ccc; border-radius: 4px; padding: 8px;">
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
                <div style="height: 50px; margin-top: 8px; display: flex; justify-content: center; align-items: center;">
                  <v-btn class="text-subtitle-1" @click="handleRunCode" color="secondary" :loading="runLoading" :disabled="runLoading">
                    Run Code
                  </v-btn>
                </div>
                <v-expand-transition>
                  <template v-if="testResults.length">
                    <v-card elevation="8" class="mt-4 pa-4 test-cases-card rounded-card" color="#2E2E2E">
                      <div v-for="(test, index) in testResults" :key="index" class="mb-3">
                        <v-card outlined class="pa-3 rounded-lg test-case-card">
                          <div class="test-case-indicator" :class="{'pass': test.output === test.expected, 'fail': test.output !== test.expected}"></div>
                          <div class="test-case-wrapper">
                            <div class="test-item rounded-lg test-case-header">
                              <strong>
                                Test Case {{ index + 1 }}: {{ test.output === test.expected ? 'Passed' : 'Failed' }}
                              </strong>
                            </div>
                            <div class="test-case-content">
                              <div class="test-item rounded-lg">
                                <strong>Input:</strong> {{ test.input }}
                              </div>
                              <div class="test-item rounded-lg">
                                <strong>Expected:</strong> {{ test.expected }}
                              </div>
                              <div class="test-item rounded-lg">
                                <strong>Output:</strong> {{ test.output }}
                              </div>
                            </div>
                          </div>
                        </v-card>
                      </div>
                    </v-card>
                  </template>
                  <template v-else>
                    <div class="mt-4 text-center" style="height: 0; overflow: hidden;">
                      Test results will appear here.
                    </div>
                  </template>
                </v-expand-transition>
              </v-card>
            </v-col>

            <!-- AI Assistant Column -->
            <v-col cols="12" md="4" style="padding: 4px;">
              <v-card elevation="8" class="pa-4 rounded-card" 
                style="width: 100%; height: calc(100vh - 230px); display: flex; flex-direction: column;">
                <div style="height: 60px;">
                  <h1 class="text-h6 text-center" style="margin: 0;">AI Assistant</h1>
                </div>
                <div style="height: calc(100% - 110px); overflow-y: auto; border: 1px solid #ccc; border-radius: 4px; background-color: #2E2E2E; color: white; padding: 8px;">
                  <div v-if="outputText">
                    {{ outputText }}
                  </div>
                  <div v-else>
                    Ask me for help with your code!
                  </div>
                </div>
                <div style="height: 200px; margin-top: 4px; display: flex; flex-direction: column; gap: 4px;">
                  <v-textarea
                    v-model="helpText"
                    placeholder="Ask for help (e.g., 'How do I write a function?')"
                    rows="1"
                    style="max-width: 100%; height: 100px; overflow-y: auto;"
                  ></v-textarea>
                  <v-btn @click="handleHelp" height="30px" color="info" class="text-subtitle-1" block :loading="helpLoading" :disabled="helpLoading">
                    Get help
                  </v-btn>
                </div>
              </v-card>
            </v-col>
          </v-row>
        </div>

        <!-- Bottom Bar: Submit Button and Timer -->
        <div style="flex: 0 0 auto; position: relative; height: 60px;">
          <div style="position: absolute; left: 50%; transform: translate(-50%, -50%); top: 50%;">
            <v-btn class="text-subtitle-1" @click="handleSubmit" color="primary" :loading="loading" :disabled="loading">
              Submit Code
            </v-btn>
          </div>
          <div style="position: absolute; right: 8px; top: 50%; transform: translateY(-50%); font-size: 1rem; font-weight: bold; color: #0d1b2a;">
            {{ formattedTime }}
          </div>
        </div>
      </div>
    </v-container>
  </v-main>
</template>

<script>
import api from '../axios';
import { Codemirror } from 'vue-codemirror';
import { python } from '@codemirror/lang-python';
import { oneDark } from '@codemirror/theme-one-dark';

export default {
  name: 'CodeEditorPage',
  components: { Codemirror },
  data() {
    return {
      pageNum: '1',
      code: '# Write your Python code here\n',
      question: '',
      extensions: [python(), oneDark],
      view: null,
      outputText: '',
      loading: false,
      runLoading: false,
      helpLoading: false,
      testResults: [],
      helpText: '',
      timeLeft: 600, // default to 600 seconds; will be updated from API
      timerInterval: null,
      autosaveInterval: null, // Interval for auto-saving code
    };
  },
  computed: {
    formattedTime() {
      const minutes = Math.floor(this.timeLeft / 60);
      const seconds = this.timeLeft % 60;
      return `${minutes.toString().padStart(2, '0')}:${seconds
        .toString()
        .padStart(2, '0')}`;
    },
  },
  created() {
    const token = this.getAccessToken();
    console.log("Token:", token);
    if (this.$route.state?.user) {
      this.user = this.$route.state.user;
    }
    if (!token) {
      this.$router.push({ name: 'Login' });
    }
    // Fetch question data with token
    api.get(`/question/${this.pageNum}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(response => {
        if (response.data.status === 'success') {
          this.question = response.data.question.question_text;
        } else {
          console.error(response.data.message);
        }
      })
      .catch(error => console.error(error));

    // Fetch programming code and timer data with token
    api.get(`/programming/${this.pageNum}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(response => {
        if (response.data.status === 'success') {
          this.code = response.data.code;
          // Convert timer_duration (minutes) to seconds
          const durationMinutes = response.data.timer_duration;
          this.timeLeft = durationMinutes * 60;
        } else {
          console.error(response.data.message);
        }
      })
      .catch(error => console.error(error));

    // Start the countdown timer (updates every second)
    this.timerInterval = setInterval(() => {
      if (this.timeLeft > 0) {
        this.timeLeft--;
      } else {
        clearInterval(this.timerInterval);
      }
    }, 1000);

    // Start autosave every 20 seconds
    this.autosaveInterval = setInterval(() => {
      this.autosaveCode();
    }, 20000);
  },
  beforeUnmount() {
    clearInterval(this.timerInterval);
    clearInterval(this.autosaveInterval);
  },
  methods: {
    logout() {
      // Clear the access token cookie and redirect to Login page.
      document.cookie = 'access_token=; Max-Age=0';
      this.$router.replace({ name: 'Login' });
    },
    // Helper to extract the access token from cookies
    getAccessToken() {
      const value = `; ${document.cookie}`;
      const parts = value.split(`; access_token=`);
      if (parts.length === 2) return parts.pop().split(';').shift();
      return null;
    },
    handleReady(payload) {
      this.view = payload.view;
    },
    handleSubmit() {
      this.loading = true;
      const token = this.getAccessToken();
      api.post(`/programming/${this.pageNum}/submit`, { code: this.code }, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(response => {
          this.outputText = 'Code submitted:\n' + this.code;
          console.log('Code submitted successfully:', response.data);
        })
        .catch(error => console.error(error))
        .finally(() => {
          this.loading = false;
        });
    },
    handleRunCode() {
      this.runLoading = true;
      const token = this.getAccessToken();
      api.post(`/programming/${this.pageNum}/run`, { code: this.code }, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(response => {
          if (response.data.test_results) {
            this.testResults = response.data.test_results;
          }
        })
        .catch(error => console.error(error))
        .finally(() => {
          this.runLoading = false;
        });
    },
    handleHelp() {
      this.helpLoading = true;
      const token = this.getAccessToken();
      api.post(`/programming/${this.pageNum}/prompt`, { prompt: this.helpText, code: this.code }, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(response => {
          if (response.data.ai_response) {
            this.outputText += "\nHelp: " + response.data.ai_response;
          }
        })
        .catch(error => console.error(error))
        .finally(() => {
          this.helpText = '';
          this.helpLoading = false;
        });
    },
    autosaveCode() {
      const token = this.getAccessToken();
      if (!token) return;
      api.post(`/programming/${this.pageNum}/autosave`, { code: this.code }, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(response => {
          console.log('Code auto-saved:', response.data.message);
        })
        .catch(error => {
          console.error('Autosave error:', error);
        });
    },
  },
};
</script>

<style scoped>
.editor-background {
  background-color: #dee2e6;
}
.timer {
  font-size: 1rem;
  font-weight: bold;
  color: #0d1b2a;
}
.test-cases-card {
  overflow-y: auto;
  max-height: 400px;
  transition: max-height 0.5s ease-in-out;
  padding-right: 10px;
}
.test-case-card {
  display: flex;
  align-items: stretch;
  position: relative;
}
.test-case-indicator {
  width: 2px;
  align-self: stretch;
  margin-right: 10px;
}
.test-case-indicator.pass {
  background-color: #4caf50;
}
.test-case-indicator.fail {
  background-color: #f44336;
}
.test-case-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.test-case-header {
  background-color: #dee2e6;
  padding: 6px 10px;
  border-radius: 4px;
  font-family: monospace;
}
.test-case-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.test-item {
  background-color: #dee2e6;
  padding: 6px 10px;
  border-radius: 4px;
  font-family: monospace;
}
.rounded-card {
  border-radius: 12px;
}
</style>
