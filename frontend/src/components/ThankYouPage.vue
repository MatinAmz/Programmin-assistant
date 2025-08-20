<template>
  <v-main class="thank-you-background">
    <!-- Remove fluid from the container to avoid it stretching full width and add center alignment -->
    <v-container class="pa-4 d-flex justify-center" style="text-align: center;">
      <v-card elevation="8" class="pa-6 rounded-card">
        <!-- Display the user's name fetched from the API -->
        <h1 class="text-h4">Thank You, {{ userName }}!</h1>
        <p class="pa-2 text-body-1">
          We appreciate your feedback and participation.
        </p>
        <!-- Display the formatted timestamp if available -->
        <p v-if="timestamp" class="pa-2 text-caption">
          Completed at: {{ formattedTimestamp }}
        </p>
        <!-- Display any error messages if applicable -->
        <p v-if="error" class="text-error">{{ error }}</p>
        <v-btn class="text-subtitle-1" color="primary" @click="goHome">
          Return Home
        </v-btn>
      </v-card>
    </v-container>
  </v-main>
</template>

<script>
import api from '../axios';

export default {
  name: 'ThankYouPage',
  data() {
    return {
      userName: '',
      timestamp: '',
      error: ''
    };
  },
  computed: {
    // Format the timestamp using the built-in Date API.
    formattedTimestamp() {
      if (!this.timestamp) return '';
      const date = new Date(this.timestamp);
      return date.toLocaleString(); // e.g. "4/14/2025, 3:30:00 PM"
    }
  },
  methods: {
    // Helper to retrieve the access token from cookies.
    getAccessToken() {
      const value = `; ${document.cookie}`;
      const parts = value.split(`; access_token=`);
      if (parts.length === 2) return parts.pop().split(';').shift();
      return null;
    },
    // Fetch the completion data using the access token.
    async fetchCompletionData() {
      try {
        const token = this.getAccessToken();
        const response = await api.get('/completion', {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (response.data.status === 'success') {
          this.userName = response.data.completion.user_name;
          this.timestamp = response.data.completion.timestamp;
        } else {
          this.error = 'Failed to load data.';
        }
      } catch (error) {
        console.error('Error fetching completion data:', error);
        if (error.response && error.response.status === 401) {
          this.$router.push({ name: 'Login' });
        } else {
          this.error = 'An error occurred while fetching data.';
        }
      }
    },
    // Redirect the user to the Login page.
    goHome() {
      document.cookie = "access_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
      this.$router.replace({ name: 'Login' });
    }
  },
  // Automatically fetch the data when the component is mounted.
  mounted() {
    this.fetchCompletionData();
  }
};
</script>

<style scoped>
.thank-you-background {
  background-color: #f5f5f5;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
/* Constrain the card width and center it; add extra padding if needed */
.rounded-card {
  border-radius: 12px;
  max-width: 600px; /* Limits the width of the card */
  width: 100%;
  margin: auto;
  /* Additional inner padding can be controlled via pa-6 class and extra custom padding here if desired */
  padding: 24px;
}
</style>
