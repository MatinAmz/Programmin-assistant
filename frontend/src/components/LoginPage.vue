<template>
  <v-main class="login-background">
    <v-container fluid class="d-flex align-center justify-center fill-height pa-0">
      <v-row align="center" justify="center" class="ma-0 pa-0 fill-height">
        <v-col cols="12" sm="8" md="5" class="d-flex flex-column align-center justify-center">
          <!-- Card Container -->
          <div class="tab-card-container" style="width: 100%; max-width: 500px;">
            <!-- Show Login/Register Card if Forgot Password is not active -->
            <div v-if="!forgotPasswordActive">
              <!-- Tab navigation -->
              <v-tabs v-model="tab" background-color="#FFFFFF" grow class="light-tabs tab-margin">
                <v-tab value="login">Login</v-tab>
                <v-tab value="register">Register</v-tab>
              </v-tabs>

              <v-window v-model="tab">
                <!-- Login Form -->
                <v-window-item value="login">
                  <h1 class="text-h5 text-center mb-6">Log into your account</h1>
                  <v-card elevation="4" class="pa-6 ma-2 rounded-card" color="#f5f5f5" >
                    <v-form v-model="valid" @submit.prevent="handleLogin">
                      <v-text-field
                        v-model="email"
                        label="Email"
                        type="email"
                        :rules="[rules.required, rules.email]"
                        outlined
                        dense
                        color="primary"
                        class="mb-4"
                        hide-details="auto"
                      ></v-text-field>

                      <v-text-field
                        v-model="password"
                        label="Password"
                        type="password"
                        :rules="[rules.required]"
                        outlined
                        dense
                        color="primary"
                        class="mb-1"
                        hide-details="auto"
                      ></v-text-field>

                      <!-- Error Message on Login Failure -->
                      <div v-if="loginError" class="error-text" style="color: red; margin-bottom: 8px;">
                        {{ loginError }}
                      </div>

                      <div class="d-flex align-center justify-space-between mb-4">
                        <v-checkbox
                          v-model="rememberMe"
                          label="Remember me"
                          color="primary"
                          dense
                        ></v-checkbox>
                        <!-- Forgot Password link appears only after a failed login -->
                        <div v-if="showForgotLink" class="forgot-link ml-2" @click="forgotPasswordActive = true" style="cursor: pointer; color: #1976D2;">
                          Forgot Password?
                        </div>
                      </div>

                      <v-btn type="submit" color="primary" block class="mb-4 text-subtitle-1" :disabled="!valid">
                        Log In
                      </v-btn>

                      <!-- Microsoft Login Button -->
                      <v-btn block class="mb-4 text-subtitle-1" color="white" outlined @click="handleMicrosoftLogin">
                        <v-img
                          src="/assets/microsoft.png"
                          min-width="24"
                          min-height="24"
                          class="mr-2"
                          contain
                        ></v-img>
                        Microsoft Login
                      </v-btn>

                      <v-btn text class="text-subtitle-1" color="primary" block @click="tab = 'register'">
                        Sign up
                      </v-btn>
                    </v-form>
                  </v-card>
                </v-window-item>

                <!-- Register Form -->
                <v-window-item value="register">
                  <h1 class="text-h5 text-center mb-6">Create a new account</h1>
                  <v-card elevation="4" class="pa-6 ma-2 rounded-card" color="#f5f5f5">
                    <v-form v-model="valid" @submit.prevent="handleRegister">
                      <v-text-field
                        v-model="firstName"
                        label="First Name"
                        :rules="[rules.required]"
                        outlined
                        dense
                        color="primary"
                        class="mb-4"
                        hide-details="auto"
                      ></v-text-field>

                      <v-text-field
                        v-model="lastName"
                        label="Last Name"
                        :rules="[rules.required]"
                        outlined
                        dense
                        color="primary"
                        class="mb-4"
                        hide-details="auto"
                      ></v-text-field>

                      <v-text-field
                        v-model="email"
                        label="Email"
                        type="email"
                        :rules="[rules.required, rules.email]"
                        outlined
                        dense
                        color="primary"
                        class="mb-4"
                        hide-details="auto"
                      ></v-text-field>

                      <v-text-field
                        v-model="password"
                        label="Password"
                        type="password"
                        :rules="[rules.required]"
                        outlined
                        dense
                        color="primary"
                        class="mb-4"
                        hide-details="auto"
                      ></v-text-field>

                      <v-btn type="submit" color="primary" block class="mb-4 text-subtitle-1" :disabled="!valid">
                        Register
                      </v-btn>

                      <v-btn text class="text-subtitle-1" color="primary" block @click="tab = 'login'">
                        Back to Login
                      </v-btn>
                    </v-form>
                  </v-card>
                </v-window-item>
              </v-window>
            </div>

            <!-- Forgot Password Card with Transition -->
            <v-slide-x-transition>
              <v-card v-if="forgotPasswordActive" elevation="2" class="pa-6" color="#f5f5f5" style="min-width: 100%;">
                <div class="d-flex align-center mb-4">
                  <!-- Back Icon to Return to Login -->
                  <v-btn elevation="0" icon style="background-color: transparent;" @click="forgotPasswordActive = false">
                    <v-icon>mdi-arrow-left</v-icon>
                  </v-btn>
                  <h2 class="text-h6 ml-2">Forgot Password</h2>
                </div>
                <v-form @submit.prevent="handleForgotPassword">
                  <v-text-field
                    v-model="forgotEmail"
                    label="Enter your email"
                    type="email"
                    :rules="[rules.required, rules.email]"
                    outlined
                    dense
                    color="primary"
                    class="mb-4"
                    hide-details="auto"
                  ></v-text-field>
                  <v-btn type="submit" color="primary" block class="mb-4">
                    Submit
                  </v-btn>
                </v-form>
              </v-card>
            </v-slide-x-transition>
          </div>
        </v-col>
      </v-row>
    </v-container>
  </v-main>
</template>

<script>
import api from '../axios';
import * as msal from '@azure/msal-browser';

// MSAL config (unchanged)
const msalConfig = {
  auth: {
    clientId: "c0a216b6-8b9b-4deb-95d9-fe1b7c16bced",
    authority: "https://login.microsoftonline.com/170bbabd-a2f0-4c90-ad4b-0e8f0f0c4259",
    redirectUri: "https://understand-ai.org/"
  },
  cache: {
    cacheLocation: "localStorage",
    storeAuthStateInCookie: false,
  }
};
const msalInstance = new msal.PublicClientApplication(msalConfig);

export default {
  name: 'LoginPage',
  data() {
    return {
      tab: 'login',
      email: '',
      password: '',
      firstName: '',
      lastName: '',
      rememberMe: false,
      valid: false,
      showForgotLink: false,
      forgotPasswordActive: false,
      forgotEmail: '',
      loginError: '',
      rules: {
        required: v => !!v || 'Required.',
        email: v => /.+@.+\..+/.test(v) || 'Invalid e-mail.',
      },
    };
  },
  created() {
    msalInstance.initialize?.();
    this.loadRemembered();
    this.checkToken();
  },
  methods: {
    getAccessToken() {
      const parts = (`; ${document.cookie}`).split(`; access_token=`);
      return parts.length === 2 ? parts.pop().split(';').shift() : null;
    },
    async checkToken() {
      try {
        const token = this.getAccessToken();
        await api.get('check-token', {
          headers: { Authorization: `Bearer ${token}` },
          withCredentials: true,
        });
        // valid token → skip ahead
        this.$router.replace({ name: 'PreSurvey' });
      } catch {
        // no session, stay here
      }
    },

    async handleLogin() {
      this.loginError = '';
      try {
        const { data } = await api.post('login', {
          email: this.email,
          password: this.password,
        }, { withCredentials: true });

        if (data.status === 'success') {
          // store token & optionally remember
          const token = data.access_token;
          const maxAge = (this.rememberMe ? 7 : 1) * 24 * 60 * 60;
          document.cookie = `access_token=${token}; path=/; max-age=${maxAge}; samesite=Lax`;
          localStorage.setItem('access_token', token);
          if (this.rememberMe) {
            localStorage.setItem('rememberedEmail', this.email);
            localStorage.setItem('rememberedPassword', this.password);
          } else {
            localStorage.removeItem('rememberedEmail');
            localStorage.removeItem('rememberedPassword');
          }

          // pick next route based on flags
          const {
            presurvey_submitted,
            programming_q1_submitted,
            programming_q2_submitted
          } = data;

          let next;
          if (!presurvey_submitted) {
            next = { name: 'PreSurvey' };
          } else if (!programming_q1_submitted) {
            next = { name: 'Editor', params: { questionId: '1' } };
          } else if (!programming_q2_submitted) {
            next = { name: 'Editor', params: { questionId: '2' } };
          } else {
            next = { name: 'PostSurvey' };
          }

          this.showForgotLink = false;
          this.$router.replace(next);

        } else {
          this.loginError = data.message || 'Username or password incorrect';
          this.showForgotLink = true;
        }

      } catch (err) {
        this.loginError = 'Username or password incorrect';
        this.showForgotLink = true;
        console.error(err);
      }
    },

    async handleMicrosoftLogin() {
      this.loginError = '';
      try {
        const loginResponse = await msalInstance.loginPopup({
          scopes: ["User.Read", "email", "profile"]
        });
        const account = loginResponse.account;
        const email = account.username;
        const name = account.name;

        const { data } = await api.post('microsoft_login',
          { email, name },
          { withCredentials: true }
        );

        if (data.status === 'success') {
          const token = data.access_token;
          const maxAge = (this.rememberMe ? 7 : 1) * 24 * 60 * 60;
          document.cookie = `access_token=${token}; path=/; max-age=${maxAge}; samesite=Lax`;
          localStorage.setItem('access_token', token);

          const {
            presurvey_submitted,
            programming_q1_submitted,
            programming_q2_submitted
          } = data;

          let next;
          if (!presurvey_submitted) {
            next = { name: 'PreSurvey' };
          } else if (!programming_q1_submitted) {
            next = { name: 'Editor', params: { questionId: '1' } };
          } else if (!programming_q2_submitted) {
            next = { name: 'Editor', params: { questionId: '2' } };
          } else {
            next = { name: 'PostSurvey' };
          }

          this.showForgotLink = false;
          this.$router.replace(next);

        } else {
          this.loginError = data.message || 'Microsoft login error';
          this.showForgotLink = true;
        }

      } catch (err) {
        console.error(err);
        this.loginError = 'Microsoft login error. Please try again.';
        this.showForgotLink = true;
      }
    },

    async handleRegister() {
      const fullName = `${this.firstName} ${this.lastName}`;
      try {
        const { data } = await api.post('register', {
          name: fullName, email: this.email, password: this.password
        });
        if (data.status === 'success') {
          alert(data.message);
          this.tab = 'login';
        } else {
          alert(`Registration failed: ${data.message}`);
        }
      } catch (err) {
        alert('Registration failed: ' +
          (err.response?.data?.message || err.message));
      }
    },

    async handleForgotPassword() {
      try {
        const { data } = await api.post('forgot-password', { email: this.forgotEmail });
        if (data.status === 'success') {
          alert(data.message);
          this.forgotPasswordActive = false;
          this.forgotEmail = '';
        } else {
          alert(`Error: ${data.message}`);
        }
      } catch (err) {
        alert('Password reset failed: ' +
          (err.response?.data?.message || err.message));
      }
    },

    loadRemembered() {
      const re = localStorage.getItem('rememberedEmail');
      const rp = localStorage.getItem('rememberedPassword');
      if (re && rp) {
        this.email = re;
        this.password = rp;
        this.rememberMe = true;
      }
    },
  },
};
</script>

<style scoped>
.rounded-card { border-radius: 12px; overflow: visible; }
.tab-card-container { width: 100%; max-width: 400px; margin: 0 auto; padding: 16px; overflow: visible; }
.tab-margin { margin-bottom: 16px; }
.mr-2 { margin-right: 8px; }
.forgot-link { font-size: 0.875rem; text-decoration: underline; }
.error-text { font-size: 0.875rem; }
</style>
