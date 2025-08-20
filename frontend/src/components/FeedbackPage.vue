<template>
  <v-main class="feedback-background">
    <!-- Header Section (app bar occupies its space automatically with 'app' prop) -->
    <v-app-bar app color="white" elevation="2" class="px-4">
      <h1 class="text-h5 font-weight-bold" style="color: #1b263b;">Feedback Analysis</h1>
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

    <!-- Page Wrapper: fills viewport below app bar -->
    <div class="page-wrapper pa-2">
      <!-- Cards Wrapper: two cards side by side, filling available vertical space -->
      <div class="cards-wrapper" >
        <v-row dense v-if="feedback.user_id" class="fill-height">
          <!-- Left Card: AI Usage Feedback (shrink-wrapped) -->
          <v-col cols="auto" class="d-flex justify-center align-stretch">
            <v-card elevation="8"
              class="ma-4 pa-4 rounded-card custom-feedback-card fill-height text-center card-margin"
              style="width: fit-content;"
            >
              <!-- Flex container for vertical layout -->
              <div class="d-flex flex-column fill-height">
                <!-- Top section: header and list items -->
                <div>
                  <h2 class="text-h6">AI Usage Feedback</h2>
                  <v-list dense class="text-left">
                    <v-list-item>
                      <v-list-item-content>
                        <v-list-item-title>
                          <span class="label">Personal Usage Count:</span>
                          <span class="value">{{ feedback.personal_usage_count }}</span>
                        </v-list-item-title>
                      </v-list-item-content>
                    </v-list-item>
                    <v-list-item>
                      <v-list-item-content>
                        <v-list-item-title>
                          <span class="label">Session Duration:</span>
                          <span class="value">{{ feedback.session_duration_minutes }} minutes</span>
                        </v-list-item-title>
                      </v-list-item-content>
                    </v-list-item>
                    <v-list-item v-if="feedback.session_start">
                      <v-list-item-content>
                        <v-list-item-title>
                          <span class="label">Session Start:</span>
                          <span class="value">{{ formattedDate(feedback.session_start) }}</span>
                        </v-list-item-title>
                      </v-list-item-content>
                    </v-list-item>
                    <v-list-item v-if="feedback.session_end">
                      <v-list-item-content>
                        <v-list-item-title>
                          <span class="label">Session End:</span>
                          <span class="value">{{ formattedDate(feedback.session_end) }}</span>
                        </v-list-item-title>
                      </v-list-item-content>
                    </v-list-item>
                  </v-list>
                </div>
                <!-- Bottom section: takes remaining space and centers the progress bar -->
                <div class="flex-grow-1 d-flex flex-column align-center justify-center">
                  <span class="label" style="margin-bottom: 8px;">Your AI Usage Compared to Others:</span>
                  <v-progress-circular
                    :model-value="feedback.usage_percentage"
                    class="pa-8"
                    size="120"
                    width="15"
                    color="#023e8a"
                    background-color="lightgray"
                  >
                    <div>
                      <div style="color: #023e8a; font-weight: bold; font-size: 24px;">
                        {{ feedback.usage_percentage }}%
                      </div>
                      <div style="color: gray; font-weight: bold; font-size: 12px;">
                        of class average
                      </div>
                    </div>
                  </v-progress-circular>
                </div>
              </div>
            </v-card>
          </v-col>

          <!-- Right Card: AI Interactions Chart (expands to fill available width) -->
          <v-col class="d-flex flex-grow-1">
            <v-card elevation="8" class="ma-4 pa-6 rounded-card fill-height card-margin" style="width: 100%;">
              <h2 class="text-h6">Your AI Usage During this Question</h2>
              <div 
                class="chart-container" 
                style="position: relative; background-color: #f5f5f5; padding: 16px; width: 100%;">
                <canvas id="aiInteractionsChart"></canvas>
              </div>
            </v-card>
          </v-col>
        </v-row>
      </div>
      <!-- Next Button fixed at the bottom of the page (outside cards wrapper) -->
      <div class="next-button-wrapper">
        <v-row dense>
          <v-col class="text-center">
            <v-btn class="text-subtitle-1" color="primary" @click="goToNext">
              Next
            </v-btn>
          </v-col>
        </v-row>
      </div>
    </div>
  </v-main>
</template>

<script>
import api from '../axios';
import { Chart } from 'chart.js/auto';

export default {
  name: 'FeedbackPage',
  data() {
    return {
      feedback: {
        user_id: '',
        question_id: '',
        personal_usage_count: 0,
        usage_percentage: 0,
        session_duration_minutes: 0,
        session_start: null,
        session_end: null,
        time_data: { labels: [], values: [] },
      },
      nextInfo: { page_num: '' },
      sparklineLabels: [],
      sparklineValues: [],
      chart: null,
    };
  },
  created() {
    const token = this.getAccessToken();
    if (!token) {
      this.$router.push({ name: 'Login' });
      return;
    }
    const questionId =
      this.$route.params.questionId ||
      (this.$route.state && this.$route.state.questionId) ||
      '1';
    this.fetchFeedback(questionId);
  },
  mounted() {
    // Wait for the canvas element to be rendered before creating the chart.
    this.$nextTick(() => {
      this.waitForCanvasAndCreateChart();
    });
  },
  watch: {
    sparklineLabels(newLabels) {
      if (this.chart) {
        this.chart.data.labels = newLabels;
        this.chart.update();
      }
    },
    sparklineValues(newValues) {
      if (this.chart) {
        this.chart.data.datasets[0].data = newValues;
        this.chart.update();
      }
    },
  },
  methods: {
    logout() {
      document.cookie = "access_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
      this.$router.replace({ name: 'Login' });
    },
    getAccessToken() {
      const value = `; ${document.cookie}`;
      const parts = value.split(`; access_token=`);
      if (parts.length === 2) return parts.pop().split(';').shift();
      return null;
    },
    fetchFeedback(questionId) {
      const token = this.getAccessToken();
      api.get(`/feedback/${questionId}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((response) => {
          if (response.data.status === 'success') {
            const feedbackData = response.data.feedback;
            this.feedback = feedbackData;
            this.sparklineLabels = feedbackData.time_data.labels;
            this.sparklineValues = feedbackData.time_data.values;
            this.nextInfo = response.data.next;
          } else {
            console.error(response.data.message);
          }
        })
        .catch((error) => console.error(error));
    },
    waitForCanvasAndCreateChart() {
      const canvas = document.getElementById('aiInteractionsChart');
      if (!canvas) {
        setTimeout(() => {
          this.waitForCanvasAndCreateChart();
        }, 100);
      } else {
        this.createChart();
      }
    },
    createChart() {
      const canvas = document.getElementById('aiInteractionsChart');
      const ctx = canvas.getContext('2d');
      this.chart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: this.sparklineLabels,
          datasets: [{
            label: 'AI Interactions',
            data: this.sparklineValues,
            borderColor: '#586ba4',
            borderWidth: 3,
            fill: false,
            pointRadius: 3,
            pointBackgroundColor: 'black',
          }],
        },
        options: {
          scales: {
            x: {
              title: {
                display: true,
                text: 'Minutes into question',
                color: 'black',
              },
              grid: {
                display: true,
                color: 'rgba(211,211,211, 0.8)',
              },
              ticks: {
                color: 'black',
                padding: 10,
              },
            },
            y: {
              min: 0,
              max: 5,
              ticks: {
                stepSize: 1,
                color: 'black',
                padding: 10,
              },
              grid: {
                display: true,
                color: 'rgba(211,211,211, 0.8)',
              },
              title: {
                display: true,
                text: 'Number of interactions',
                color: 'black',
              },
            },
          },
          plugins: {
            legend: { display: false },
          },
        },
      });
    },
    goToNext() {
      if (this.nextInfo.page_num) {
        this.$router.push({
          name: 'Editor',
          params: { questionId: this.nextInfo.page_num },
        });
      } else {
        this.$router.push({ name: 'PostSurvey' });
      }
    },
    formattedDate(dateVal) {
      if (!dateVal) return '';
      const dateStr = typeof dateVal === 'object' && dateVal.$date ? dateVal.$date : dateVal;
      return new Date(dateStr).toLocaleString();
    },
  },
};
</script>

<style scoped>
.feedback-background {
  background-color: #f0f2f5;
}

/* Page wrapper fills space below the app bar (assumed height 64px) */
.page-wrapper {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 64px);
}

/* Cards wrapper takes available space minus the next button; now vertically scrollable */
.cards-wrapper {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

/* Let the two cards fill the height provided */
.fill-height {
  height: 100%;
}

/* Feedback card custom padding (unchanged) */
.custom-feedback-card {
  text-align: left;
}

/* Rounded card common style */
.rounded-card {
  border-radius: 12px;
}

/* New class for adding margin to cards */
.card-margin {
  margin: 16px;
}

/* Label and value styles for list items */
.label {
  font-weight: 700;
  margin-right: 4px;
}
.value {
  font-weight: 400;
}

/* Chart container fills the card's remaining height and gets a rounded border */
.chart-container {
  height: calc(100% - 48px);
  border: 2px solid #ddd; /* Adjust the border color and width as needed */
  border-radius: 12px;
  overflow: hidden; /* Ensures the content (chart) respects the rounded corners */
}

.next-button-wrapper {
  background: transparent; /* Next button wrapper background transparent */
  height: 60px;
  flex-shrink: 0;
  padding: 20px 0;
}
</style>
