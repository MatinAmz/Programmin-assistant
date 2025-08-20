<template>
  <v-main class="login-background">
    <v-container fluid class="pa-0">
      <!-- Header Section -->
      <v-app-bar app color="white" elevation="2" class="px-4">
        <h1 class="text-h5 font-weight-bold" style="color: #1b263b;">Post Survey</h1>
        <v-spacer></v-spacer>
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
      <v-row class="ma-0" align="center" justify="center">
        <v-col cols="12">
          <div class="tab-card-container">
            <v-card elevation="8" class="pa-6 rounded-card" color="white">
              <v-form v-model="valid" @submit.prevent="submitSurvey" ref="surveyForm">
                <!-- Non-Likert Questions -->
                <div
                  v-for="question in nonLikertQuestions"
                  :key="question.id"
                  class="question-divider"
                >
                  <!-- Multiple Choice (Radio) -->
                  <v-radio-group
                    v-if="question.question_type === 'multiple_choice'"
                    v-model="answers[question.id]"
                    :label="question.question_text"
                    hide-details="true"
                    class="ml-4"
                    :error="
                      submittedOnce &&
                      question.required &&
                      (!answers[question.id] ||
                        answers[question.id].toString().trim() === '')
                    "
                  >
                    <v-radio
                      v-for="(option, optIndex) in question.options"
                      :key="optIndex"
                      :label="option"
                      :value="option"
                    ></v-radio>
                  </v-radio-group>

                  <!-- Text Input -->
                  <v-text-field
                    v-if="question.question_type === 'text_input' || question.question_type === 'text'"
                    v-model="answers[question.id]"
                    :label="question.question_text"
                    outlined
                    dense
                    color="primary"
                    hide-details="true"
                    :error="
                      submittedOnce &&
                      question.required &&
                      (!answers[question.id] ||
                        answers[question.id].toString().trim() === '')
                    "
                    :type="question.unit === 'years' ? 'number' : 'text'"
                  ></v-text-field>

                  <!-- Checkbox Group -->
                  <div
                    v-if="question.question_type === 'checkbox'"
                    class="mb-4"
                    :class="{
                      'input-error': submittedOnce &&
                        question.required &&
                        (!answers[question.id] ||
                          !Array.isArray(answers[question.id]) ||
                          answers[question.id].length === 0)
                    }"
                  >
                    <div class="mb-4">{{ question.question_text }}</div>
                    <v-checkbox
                      v-for="(option, optIndex) in question.options"
                      :key="optIndex"
                      :label="option.label"
                      :value="option.value"
                      v-model="answers[question.id]"
                      color="primary"
                      hide-details="true"
                    ></v-checkbox>
                  </div>
                </div>

                <!-- Likert Scale Questions as a Table -->
                <div v-if="likertQuestions.length" class="question-divider">
                  <h2 class="text-h6 mb-4">
                    Please select your answer for each statement:
                  </h2>
                  <!-- Wrapping table in a scrollable container -->
                  <div class="scrollable-table">
                    <v-simple-table class="likert-table">
                      <template v-slot:default>
                        <thead>
                          <tr>
                            <!-- The first column now auto‐sizes to its content -->
                            <th class="table-cell">Question</th>
                            <th
                              v-for="(option, idx) in likertOptions"
                              :key="idx"
                              class="table-cell text-center"
                            >
                              {{ option }}
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr
                            v-for="question in likertQuestions"
                            :key="question.id"
                            :class="{
                              'input-error':
                                submittedOnce &&
                                question.required &&
                                (!answers[question.id] ||
                                  answers[question.id].toString().trim() === '')
                            }"
                            class="table-row"
                          >
                            <td class="table-cell" style="white-space: normal;">
                              {{ question.question_text }}
                            </td>
                            <td
                              v-for="(option, optIndex) in question.options"
                              :key="optIndex"
                              class="table-cell text-center"
                            >
                              <!-- Likert radio buttons wrapped in a radio group -->
                              <v-radio-group
                                v-model="answers[question.id]"
                                row
                                hide-details="true"
                                :error="
                                  submittedOnce &&
                                  question.required &&
                                  (!answers[question.id] ||
                                    answers[question.id].toString().trim() === '')
                                "
                                class="d-flex justify-center"
                              >
                                <v-radio
                                  :value="option"
                                  class="d-flex justify-center"
                                ></v-radio>
                              </v-radio-group>
                            </td>
                          </tr>
                        </tbody>
                      </template>
                    </v-simple-table>
                  </div>
                </div>

                <!-- Submit Button (always clickable) -->
                <div class="d-flex justify-center">
                  <v-btn
                    type="button"
                    color="blue"
                    class="mb-4 text-subtitle-1 px-5"
                    :loading="loading"
                    @click="handleSubmit"
                  >
                    Submit Survey
                  </v-btn>
                </div>
              </v-form>
            </v-card>
          </div>
        </v-col>
      </v-row>

      <!-- Overlay Alert -->
      <v-snackbar
        v-model="showOverlayAlert"
        timeout="3000"
        color="red"
        top
        style="position: fixed; top: 92%; left: 50%; transform: translate(-50%, -50%);"
      >
        <v-icon left>mdi-alert</v-icon>
        Please answer all questions.
      </v-snackbar>
    </v-container>
  </v-main>
</template>

<script>
import api from '../axios';

export default {
  name: 'PostSurvey',
  data() {
    return {
      user: null,
      valid: false,
      loading: false,
      questions: [],
      answers: {},
      submittedOnce: false,
      showOverlayAlert: false,
      rules: {
        required: v => !!v || 'Required.',
      },
    };
  },
  computed: {
    nonLikertQuestions() {
      return this.questions.filter(q => q.question_type !== 'likert_scale');
    },
    likertQuestions() {
      return this.questions.filter(q => q.question_type === 'likert_scale');
    },
    likertOptions() {
      return this.likertQuestions.length ? this.likertQuestions[0].options : [];
    },
    allRequiredAnswered() {
      return this.questions.every(question => {
        if (!question.required) return true;
        const answer = this.answers[question.id];
        if (question.question_type === 'checkbox') {
          return Array.isArray(answer) && answer.length > 0;
        }
        return answer && answer.toString().trim() !== '';
      });
    },
  },
  async created() {
    const token = this.getAccessToken();
    if (this.$route.state?.user) {
      this.user = this.$route.state.user;
    }
    if (!token) {
      this.$router.push({ name: 'Login' });
    } else {
      await this.fetchQuestions();
    }
  },
  methods: {
    getAccessToken() {
      const value = `; ${document.cookie}`;
      const parts = value.split(`; access_token=`);
      if (parts.length === 2) return parts.pop().split(';').shift();
      return null;
    },
    async fetchQuestions() {
      try {
        const token = this.getAccessToken();
        const response = await api.get('/postSurvey', {
          headers: { Authorization: `Bearer ${token}` },
        });
        this.questions = response.data.questions;
        this.questions.forEach(q => {
          this.answers[q.id] = q.question_type === 'checkbox' ? [] : '';
        });
      } catch (error) {
        console.error(error);
        if (error.response?.status === 401) {
          this.$router.push({ name: 'Login' });
        }
      }
    },
    handleSubmit() {
      this.submittedOnce = true;
      this.$refs.surveyForm.validate();
      if (!this.allRequiredAnswered) {
        this.showOverlayAlert = true;
        setTimeout(() => (this.showOverlayAlert = false), 3000);
        return;
      }
      this.submitSurvey();
    },
    async submitSurvey() {
      this.loading = true;
      try {
        const payload = {};
        this.questions.forEach(q => {
          let ans = this.answers[q.id];
          if (Array.isArray(ans)) ans = ans.join(', ');
          payload[`question_${q.id}`] = ans;
        });
        const token = this.getAccessToken();
        await api.post('/postSurvey', payload, {
          headers: { Authorization: `Bearer ${token}` },
        });
        this.$router.push({ name: 'ThankYou' });
      } catch (error) {
        console.error(error);
        if (error.response?.status === 401) {
          this.$router.push({ name: 'Login' });
        }
      } finally {
        this.loading = false;
      }
    },
    logout() {
      document.cookie =
        "access_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
      this.$router.replace({ name: 'Login' });
    },
  },
};
</script>

<style scoped>
.login-background {
  background-color: #dee2e6;
}
.tab-card-container {
  width: calc(100% - 40px);
  margin: 20px;
}
.question-divider {
  padding-bottom: 10px;
  margin-bottom: 10px;
  border-bottom: 1px solid grey;
}

/* Make the first (Question) column auto‐width to fit its content */
.likert-table {
  table-layout: auto;     /* allow columns to size by content */
  width: 100%;
}
.likert-table th:first-child,
.likert-table td:first-child {
  white-space: nowrap;     /* keep question text on one line, or remove if you want wrapping */
  width: fit-content;      /* shrink to fit the longest question */
}

/* The other columns will take remaining space evenly */
.likert-table th:not(:first-child),
.likert-table td:not(:first-child) {
  width: auto;
}

.likert-table .table-cell {
  border: 1px solid #dedede;
  padding: 8px;
}
.likert-table th.table-cell {
  background-color: #f5f5f5;
}
.likert-table .table-row {
  border: 1px solid #f5f5f5;
}

.rounded-card {
  border-radius: 12px;
}
.input-error {
  border: 2px solid red;
  border-radius: 4px;
  padding: 4px;
}
/* Scrollable table container for responsiveness */
.scrollable-table {
  overflow-x: auto;
}
</style>
