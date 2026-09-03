// axios.js
import axios from 'axios';

const api = axios.create({
  baseURL: process.env.VUE_APP_API_BASE_URL,
  withCredentials: true, // This allows sending cookies (important for CSRF!)
  timeout: 10000,
});

export default api;
