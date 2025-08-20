// main.js
import { createApp } from 'vue';
import App from './App.vue';
import router from './router/index'; // Add this line
import 'vuetify/styles';
import { createVuetify } from 'vuetify';
import * as components from 'vuetify/components';
import * as directives from 'vuetify/directives';
import api from './axios';

const vuetify = createVuetify({
  components,
  directives,

});

const app = createApp(App);

app.config.globalProperties.$api = api;

// Add the router
app.use(router);
app.use(vuetify).mount('#app');