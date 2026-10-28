We want to run robotics eval via /Users/dylanler/github/nex-arm-3-cam-eval/prompt.md

The task is to control a robot arm to pick up a screw driver and place it in a bowl.

The goal of this eval is to test if more cameras input allow the models to perform better or not.a

We will test 3 models via opencode cli harness in the order of:
anthropic/claude-opus-5.5
google/gemini-4-argon
openai/gpt-6.1-sol

Every model will run at medium effort level.

The opencode harness is already set up with an openrouter API keys that should have these models.

You can run the opencode harness with the example here:

opencode run --auto --model provider/model "Your prompt here"

Remember to use --auto mode so that we can run the experiment end to end.

The prompt should only be passed to the opencode cli harness once.  The model + harness should then run the eval task end to end.

Before each eval, please make sure the robot arm is at a resting home position for consistency.  The current position is fine(make sure consistency after each eval)

Please also note down the input and output total token being passed through the opencode cli harness as well as the total cost(based on provider's own default pricing)

Create the recording metadata as a json file and put it in the directory in the same recording clip the models put the video clip.

Record any additional metadata we need in the json to have a robust experiment.  We just need to make sure the set up is consistent for all evals.

Name dir and files descriptively to allow easy organization.

We want to test evals on 3 camera combos so modify prompt.md accordingly before sending it as a prompt to the opencode cli harness.

Camera combo 1:
- top down logitech camera
- lower left corner realsense camera
- robo wrist camera

Camera combo 2:
- top down logitech camera
- robo wrist camera

Camera combo 3:
- robo wrist camera

We will test a total of 9 evals.  Complete all combo for each model first before moving to next model.  After each eval, please ring a notification audio to me so that I can reset the screwdriver position.