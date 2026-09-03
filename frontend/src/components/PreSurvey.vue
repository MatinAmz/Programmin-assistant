<template>
  <v-main class="login-background">
    <v-container fluid class="pa-0">
      <!-- Header Section -->
      <v-app-bar app color="white" elevation="2" class="px-4">
        <h1 class="text-h5 font-weight-bold" style="color: #1b263b;">Pre Survey</h1>
        <v-spacer></v-spacer>
        <v-btn class="text-subtitle-2" color="#ff758f" size="small" variant="elevated" @click="logout">
          Sign Out
        </v-btn>
      </v-app-bar>
      <v-row class="ma-0" align="center" justify="center">
        <v-col cols="12">
          <div class="tab-card-container">
            <v-card elevation="8" class="pa-6 rounded-card" color="white">
              <!-- The v-form still manages overall form validity if needed -->
              <v-form v-model="valid" @submit.prevent="submitSurvey" ref="surveyForm">
                <!-- Render non-likert questions -->
                <div
                  v-for="(question) in nonLikertQuestions"
                  :key="question.index"
                  class="question-divider"
                >
                  <!-- Multiple Choice (Radio - old format: options are strings) -->
                  <v-radio-group
                    v-if="question.question_type === 'multiple_choice'"
                    v-model="answers[question.index]"
                    :label="question.question_text"
                    hide-details="true"
                    :error="submittedOnce && question.required && !answers[question.index]"
                  >
                    <v-radio
                      v-for="(option, optIndex) in question.options"
                      :key="optIndex"
                      :label="getOptionLabel(option)"
                      :value="getOptionValue(option)"
                    ></v-radio>
                  </v-radio-group>

                  <!-- Text Input -->
                  <v-text-field
                    v-if="question.question_type === 'text_input' || question.question_type === 'text'"
                    v-model="answers[question.index]"
                    :label="question.question_text"
                    outlined
                    dense
                    color="primary"
                    hide-details="true"
                    :error="submittedOnce && question.required && (answers[question.index] === '' || answers[question.index] === null)"
                    :type="question.unit === 'years' ? 'number' : 'text'"
                  ></v-text-field>

                  <!-- Checkbox Group -->
                  <div
                    v-if="question.question_type === 'checkbox'"
                    :class="{'input-error': submittedOnce && question.required && (!answers[question.index] || answers[question.index].length === 0)}"
                    class="mb-4"
                  >
                    <div class="question-text">{{ question.question_text }}</div>
                    <v-checkbox
                      v-for="(option, optIndex) in question.options"
                      :key="optIndex"
                      :label="getOptionLabel(option)"
                      :value="getOptionValue(option)"
                      v-model="answers[question.index]"
                      color="primary"
                      hide-details="true"
                    ></v-checkbox>
                  </div>

                  <!-- Radio Group (object or string format supported) -->
                  <v-radio-group
                    v-if="question.question_type === 'radio'"
                    v-model="answers[question.index]"
                    :label="question.question_text"
                    hide-details="true"
                    :error="submittedOnce && question.required && !answers[question.index]"
                  >
                    <v-radio
                      v-for="(option, optIndex) in question.options"
                      :key="optIndex"
                      :label="getOptionLabel(option)"
                      :value="getOptionValue(option)"
                    ></v-radio>
                  </v-radio-group>

                  <!-- Fallback for unknown question types -->
                  <div v-if="!['text_input', 'text', 'multiple_choice', 'checkbox', 'radio', 'likert_scale'].includes(question.question_type)" class="mb-4">
                    <p class="question-text"><strong>Unsupported question type:</strong> {{ question.question_type }}</p>
                  </div>
                </div>

                <!-- Likert Questions -->
                <div v-if="likertQuestions.length" class="question-divider">
                  <h2 class="text-h6 mb-4">Please select your answer for each statement:</h2>
                  <div class="scrollable-table">
                    <v-simple-table class="likert-table">
                      <template v-slot:default>
                        <thead>
                          <tr>
                            <th class="table-cell">Question</th>
                            <th
                              v-for="(option, idx) in likertOptions"
                              :key="idx"
                              class="table-cell text-center"
                            >
                              {{ getOptionLabel(option) }}
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr
                            v-for="q in likertQuestions"
                            :key="q.index"
                            class="table-row"
                          >
                            <td class="table-cell">
                              {{ q.question_text }}
                            </td>
                            <td
                              v-for="(option, optIndex) in likertOptions"
                              :key="optIndex"
                              class="table-cell text-center"
                            >
                              <!-- Each cell holds one radio; all share the same v-model for the row -->
                              <v-radio-group
                                v-model="answers[q.index]"
                                row
                                hide-details="true"
                                :error="submittedOnce && q.required && !answers[q.index]"
                                class="d-flex justify-center"
                              >
                                <v-radio
                                  :value="getOptionValue(option)"
                                  class="d-flex justify-center"
                                  :label="''"
                                ></v-radio>
                              </v-radio-group>
                            </td>
                          </tr>
                        </tbody>
                      </template>
                    </v-simple-table>
                  </div>
                </div>

                <!-- Modified Submit Button (always clickable) -->
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
    </v-container>

    <!-- Snackbar -->
    <v-snackbar
      v-model="showOverlayAlert"
      timeout="3000"
      color="red"
      top
      style="position: fixed; top: 92%; left: 50%; transform: translate(-50%, -50%);"
    >
      <v-icon left>mdi-alert</v-icon>
      Please answer all the questions.
    </v-snackbar>
  </v-main>
</template>

<script>
import api from '../axios';

export default {
  name: 'PreSurvey',
  data() {
    return {
      user: null,
      valid: false,
      loading: false,
      questions: [],
      answers: {},
      // Flag to indicate that submit was attempted.
      submittedOnce: false,
      // Snackbar flag.
      showOverlayAlert: false,
      // (No visible rules since we use manual error indication)
      rules: {
        required: v => !!v || 'Required.',
      },
    };
  },
  computed: {
    // Use the questions exactly as provided; don't overwrite their .index
    nonLikertQuestions() {
      return this.questions.filter(q => q.question_type !== 'likert_scale');
    },
    likertQuestions() {
      return this.questions.filter(q => q.question_type === 'likert_scale');
    },
    likertOptions() {
      return this.likertQuestions.length
        ? this.likertQuestions[0].options
        : [];
    },
    // Check that every required question is answered using the server-provided index.
    allRequiredAnswered() {
      return this.questions.every((question) => {
        if (!question.required) return true;
        const answer = this.answers[question.index];
        if (question.question_type === 'checkbox') {
          return Array.isArray(answer) && answer.length > 0;
        }
        return answer !== '' && answer !== null && answer !== undefined;
      });
    },
  },
  async created() {
    const token = this.getAccessToken();
    if (this.$route.state?.user) {
      this.user = this.$route.state.user;
    }
    if (!token) {
      this.$router.replace({ name: 'Login' });
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
    // Normalize option for labels/values (supports strings or {label, value})
    getOptionLabel(option) {
      return typeof option === 'string' ? option : option?.label ?? '';
    },
    getOptionValue(option) {
      return typeof option === 'string' ? option : option?.value ?? option?.label ?? '';
    },
    async fetchQuestions() {
      try {
        const token = this.getAccessToken();
        const response = await api.get('presurvey', {
          headers: { Authorization: `Bearer ${token}` },
        });
        this.questions = response.data.questions;
        // Initialize answers using the server-provided question.index
        this.questions.forEach((question) => {
          if (question.question_type === 'checkbox') {
            this.answers[question.index] = [];
          } else {
            this.answers[question.index] = '';
          }
        });
      } catch (error) {
        console.error('Error fetching questions:', error);
        if (error.response && error.response.status === 401) {
          this.$router.replace({ name: 'Login' });
        }
      }
    },
    handleSubmit() {
      // Set the flag to show errors on fields that are empty
      this.submittedOnce = true;
      // Optionally, trigger form validation (if needed):
      this.$refs.surveyForm?.validate?.();
      // If any required field is not answered, show the snackbar and exit.
      if (!this.allRequiredAnswered || !this.valid) {
        this.showOverlayAlert = true;
        return;
      }
      // Otherwise, submit the survey.
      this.submitSurvey();
    },
    async submitSurvey() {
      this.loading = true;
      try {
        const formattedAnswers = this.questions.map((question) => {
          let answerValue = this.answers[question.index];
          if (Array.isArray(answerValue)) {
            answerValue = answerValue.join(', ');
          }
          return {
            // Preserve the server's index as the id
            questionId: question.index,
            questionText: question.question_text,
            answer: answerValue,
          };
        });
        const token = this.getAccessToken();
        await api.post('/presurvey', { answers: formattedAnswers }, {
          headers: { Authorization: `Bearer ${token}` },
        });
        this.$router.replace({ name: 'Editor', params: { questionId: '1' } });
      } catch (error) {
        console.error('Submission error:', error);
        if (error.response && error.response.status === 401) {
          this.$router.replace({ name: 'Login' });
        }
      } finally {
        this.loading = false;
      }
    },
    logout() {
      document.cookie = "access_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
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
/* Apply uniform left padding and font size to all question sections */
.question-divider {
  padding: 10px 10px 10px 20px;
  margin-bottom: 10px;
  border-bottom: 1px solid grey;
  font-size: 16px;
}

/* Ensure question text in checkbox groups has the same font size */
.question-text {
  font-size: 16px;
  margin-bottom: 8px;
}

/* Likert table adjustments for uniform padding and font sizes */
.likert-table .table-cell {
  border: 1px solid #dedede;
  padding: 8px 8px 8px 20px;
  font-size: 16px;
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

.scrollable-table {
  overflow-x: auto;
}

/* Custom style for groups (like checkbox container) in error.
   You can adjust the border style and color as needed. */
.input-error {
  border: 2px solid #dd2d4a;
  border-radius: 6px;
  padding: 4px;
}
</style>
