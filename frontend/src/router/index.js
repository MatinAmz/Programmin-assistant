// src/router/index.js
import { createRouter, createWebHistory } from 'vue-router'
import LoginPage from '../components/LoginPage.vue'
import CodeEditorPage from '../components/CodeEditorPage.vue'
import PreSurvey from '../components/PreSurvey.vue'
import FeedbackPage from '../components/FeedbackPage.vue'
import PostSurvey from '../components/PostSurvey.vue'
import ThankYouPage from '../components/ThankYouPage.vue'
 
const routes = [
  {
    path: '/al-2025',
    name: 'Login',
    component: LoginPage
  },
  {
    path: '/presurvey',
    name: 'PreSurvey',
    component: PreSurvey,
  },
  {
    path: '/editor/:questionId',
    name: 'Editor',
    component: CodeEditorPage,
  },
  {
    path: '/feedback/:questionId',  // Feedback page with dynamic question ID
    name: 'FeedbackPage',
    component: FeedbackPage,
  },
  {
    path: '/postsurvey',
    name: 'PostSurvey',
    component: PostSurvey,
  },
  {
    path: '/thankyou',
    name: 'ThankYou',
    component: ThankYouPage,
  }
]
 
const router = createRouter({
  history: createWebHistory(process.env.BASE_URL),
  routes,
})
 
router.beforeEach((to, from, next) => {
  // Function to get cookie value by name
  const getCookie = (name) => {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
  };
 
  // Check if user ID exists in cookies
  const userId = getCookie('userId');
  const isAuthenticated = !!userId;
 
  // Check if route requires authentication
  if (to.matched.some(record => record.meta.requiresAuth)) {
    if (!isAuthenticated) {
      // Redirect to login if not authenticated
      next({ name: 'Login' });
    } else {
      next();
    }
  } else {
    next();
  }
 
  // Optional: Redirect authenticated users away from login/register
  if ((to.name === 'Login' || to.name === 'Register') && isAuthenticated) {
    next({ name: 'PreSurvey' });
  }
});
 
export default router;