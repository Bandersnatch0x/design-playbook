/* Real Vue 3: no React, CDN, build step, or source-writing endpoint. */
Vue.createApp({
  data() {
    return { count: 0 };
  },
  template: `
    <h1 id="queue-title" :data-render-count="count"
        :style="{ letterSpacing: count + 'px' }">Reading queue - {{ count }}</h1>
    <p>Vue owns the text and letter spacing; the bridge previews text color.</p>
    <button id="advance-queue" type="button" @click="count += 1">Advance queue</button>
  `,
}).mount("#app");
