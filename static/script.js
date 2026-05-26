function createQuestionBlock(index) {
  return `
    <article class="question-builder-card">
      <h3>Question ${index}</h3>
      <label>Question Text</label>
      <textarea name="question_text_${index}" rows="2" required></textarea>

      <div class="form-grid">
        <div>
          <label>Option A</label>
          <input type="text" name="option_a_${index}" required>
        </div>
        <div>
          <label>Option B</label>
          <input type="text" name="option_b_${index}" required>
        </div>
        <div>
          <label>Option C</label>
          <input type="text" name="option_c_${index}" required>
        </div>
        <div>
          <label>Option D</label>
          <input type="text" name="option_d_${index}" required>
        </div>
      </div>

      <label>Correct Option</label>
      <select name="correct_option_${index}" required>
        <option value="">Select Correct Option</option>
        <option value="A">A</option>
        <option value="B">B</option>
        <option value="C">C</option>
        <option value="D">D</option>
      </select>
    </article>
  `;
}

document.addEventListener("DOMContentLoaded", () => {
  const questionCountInput = document.getElementById("question_count");
  const buildButton = document.getElementById("buildQuestionsBtn");
  const questionsContainer = document.getElementById("questionsContainer");

  if (buildButton && questionCountInput && questionsContainer) {
    const renderQuestions = () => {
      const count = parseInt(questionCountInput.value, 10) || 0;
      if (count < 1 || count > 50) {
        questionsContainer.innerHTML = "";
        return;
      }

      let html = "";
      for (let i = 1; i <= count; i += 1) {
        html += createQuestionBlock(i);
      }
      questionsContainer.innerHTML = html;
    };

    buildButton.addEventListener("click", renderQuestions);
    renderQuestions();
  }

  const timerElement = document.getElementById("timeRemaining");
  const examForm = document.getElementById("examForm");
  if (timerElement && examForm) {
    let totalSeconds = (parseInt(timerElement.dataset.minutes || "0", 10) || 0) * 60;
    let interval = null;

    const updateTimer = () => {
      const mins = Math.floor(totalSeconds / 60);
      const secs = totalSeconds % 60;
      timerElement.textContent = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
      if (totalSeconds <= 0) {
        if (interval) {
          clearInterval(interval);
        }
        examForm.submit();
        return;
      }
      totalSeconds -= 1;
    };

    updateTimer();
    interval = setInterval(updateTimer, 1000);
  }
});
