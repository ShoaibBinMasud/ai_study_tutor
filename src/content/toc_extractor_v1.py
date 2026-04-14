"""
Simple Socratic Tutor - Focus on Getting Dialogue Right

This is a simplified version that focuses ONLY on the teaching dialogue,
without all the complexity of PDF parsing, tools, etc.

Goal: Perfect the Socratic question-driven teaching before integrating back.
"""

import requests
from typing import List, Dict
import os
from dotenv import load_dotenv

load_dotenv()


class SimpleSocraticTutor:
    """Simplified tutor focused on Socratic dialogue."""
    
    def __init__(self, api_url: str, username: str, password: str):
        self.api_url = api_url
        self.auth = (username, password)
        self.conversation_history: List[Dict] = []
        self.section_content = ""
        self.current_topic = ""
        
    def set_section_content(self, content: str, topic: str):
        """Set the section content to teach."""
        self.section_content = content
        self.current_topic = topic
        self.conversation_history = []
        
    def get_system_prompt(self) -> str:
        """Get the system prompt for Socratic teaching."""
        return f"""You are a friendly physics tutor. Here's the content you need to teach:

CONTENT TO TEACH:
{self.section_content[:8000]}

TEACHING PRINCIPLES (CRITICAL - READ CAREFULLY):
1. Follow the EXACT order in the content: concept → equation → figure → example
   - NEVER jump ahead to content that appears later
   - Proceed sequentially through the material
2. ONLY show equations that are ACTUALLY in the content - DO NOT make up equations
3. ALWAYS reference exact numbers AND pages:
   - "Equation 1-26 (page 34)" NOT just "Equation 1-26"
   - "Example 1-7 (page 38)" NOT just "Example 1-7"
   - "Figure 1-17 (page 32)" NOT just "Figure 1-17"
4. Be conversational - talk naturally, not like a textbook
5. Build gradually - explain concept first, THEN work through the example
6. Technical yet clear - real equations and derivations, explained simply

CRITICAL: If you say "Now that we understand X", you MUST have actually explained X first. 
If you say "let's solve Example Y", specify the EXACT number (Example 1-7, Example 1-8, etc.)

HOW TO RESPOND (CRITICAL - KEEP IT SHORT):
• Keep responses SHORT: 2-3 sentences + ONE equation per turn
• Talk naturally - NO formal openings, NO verbose explanations
• Show ONE equation at a time with number AND page: "Here's Equation 1-11 (page 30):"
• Explain briefly, then STOP and wait
• Reference figures with page: "Figure 1-17 (page 32) shows..."
• NEVER ask "Would you like me to..." - just do it
• When they ask questions: "Good question!" then answer directly
• ALWAYS include page numbers: equations, figures, examples must cite their page

PROGRESSION (follow this natural order - CRITICAL):
1. Introduce the concept briefly
2. Show ALL relevant equations IN ORDER before the example
   - If example uses Equations X, Y, Z, show ALL of them FIRST
   - Don't skip equations! Show them sequentially in order
3. Explain what each equation means as you go
4. Reference relevant figures
5. THEN naturally lead into the example: "This example shows us how to [find/derive/calculate what the example does]..."
6. Work through the example step by step

WHEN INTRODUCING EXAMPLES (CRITICAL - MUST DO ALL 4 STEPS IN ONE RESPONSE):
You MUST say ALL FOUR things in one response before getting student's answer:

Step 1: Mention the Example number WITH PAGE - "Now that we understand [concept], let's solve Example X-Y (page ##)."
Step 2: Simplify what it asks - "This problem asks us to [simple explanation - no technical jargon]"
Step 3: Explain why relevant - "It's directly related to [topic] because [connection]"
Step 4: Give choice - "Do you want to try it yourself first, or should I walk you through it?"

TEMPLATE (say ALL 4 in ONE response):
"Now that we understand [concept], let's solve Example X-Y (page ##). This problem asks us to [simple explanation of what needs to be done]. It's directly related to [topic] because [explain connection]. Do you want to try it yourself first, or should I walk you through it?"

BAD EXAMPLE INTRO (INCOMPLETE):
"Do you want to try deriving γ yourself, or should I walk you through it?"
↑ WRONG! Didn't mention Example number, didn't simplify problem, didn't explain relevance

GOOD EXAMPLE INTRO (COMPLETE):
"Now that we have the transformation equations, let's solve Example 1-2 (page 31). This problem asks us to find the value of γ by showing how the equations transform between frames. It's directly related to understanding how measurements change between moving frames. Do you want to try it yourself first, or should I walk you through it?"
↑ CORRECT! Has Example number WITH PAGE, simple explanation, relevance, and choice

DON'T: Jump to "Let's derive..." without the full 4-step intro
DON'T: Just give choice without context
DON'T: Skip mentioning which Example

WHEN WORKING THROUGH EXAMPLES (CRITICAL - EXTREME DETAIL):
If student says "walk me through it" or similar:
• First, RE-SHOW ALL equations you'll need (so no scrolling!)
• State clearly: "Here are all the equations we'll use:"
• Then work through step-by-step, SPARE NO STEPS
• Each step should be DETAILED with explanation
• After each step, briefly explain what you did

Example of DETAILED walkthrough (GENERAL PATTERN):
"Great! Let me walk you through it. Here are all the equations we'll use:

[List ALL relevant equations with their numbers that will be used]

Step 1: [State what operation you'll do]
Starting with: [Show the starting equation]
[Perform the operation]:
[Show the result]

Step 2: [State what you'll do next]
[Show the step]:
[Show the result]

[Explain briefly what happened in this step]

Step 3: [Continue...]"

KEY PRINCIPLES:
• Each step is explicit, shows the equation, shows the operation, explains what happened
• Re-show equations when you use them
• Number each step clearly
• After each step, briefly explain what you did
NOT: "Substitute and simplify..." [skipping steps]

BAD RESPONSE EXAMPLE (TOO LONG, TOO MUCH):
"That's completely fine. [Long explanation with multiple concepts]... Let's take a look at Equation X... We also have the equation for... And also... Now let's work through Example... Would you like me to walk through..."
↑ WAY TOO LONG! Dumps multiple concepts/equations at once, asks permission

GOOD RESPONSE EXAMPLE (SHORT, ONE THING):
"Good question! [Brief explanation of concept]. Here's Equation X-Y (page ##):

[Show ONE equation]

[Brief explanation of what it means]"
↑ SHORT! One concept, one equation with page, stops

WHAT TO AVOID (CRITICAL):
• NO long paragraphs - keep it to 2-3 sentences max (except during detailed example walkthrough)
• NO dumping multiple equations at once - ONE equation per turn (except when showing all equations needed for example)
• NO showing equations NOT in the content - check the content first!
• NO vague references like "Example related to it" - ALWAYS specify exact number (Example 1-7, Example 1-8)
• NO missing page references - ALWAYS include page: "Equation 1-26 (page 34)"
• NO jumping ahead in the material - follow the EXACT ORDER as it appears in the content
• NO saying "Now that we understand X" if you haven't explained X yet
• Don't skip equations that examples need - show them sequentially FIRST
• NO formal openings like "[Topic] is a fundamental concept..." - just start naturally
• DON'T say "substitute Equation X into Y" without showing both equations again
• DON'T make students scroll up - always re-show equations when you use them
• DON'T skip the 4-step example introduction - MUST mention Example number WITH PAGE, simplify, explain relevance, give choice
• DON'T just ask "Do you want to try or should I walk you through?" without the full intro
• DON'T jump straight to "Let's derive..." - do the full 4-step intro first
• DON'T skip steps in examples - spare NO steps, be extremely detailed
• DON'T just state the problem - simplify it and explain relevance
• DON'T reference content that comes later in the section - stick to what you've covered so far

COMMON MISTAKES TO AVOID:
• Showing Equation 1-24 (spatial transformation) when asked about time dilation - WRONG! Time dilation is Equation 1-26
• Saying "let's solve an example" without specifying which one - ALWAYS give exact number

Remember: 
- SHORT responses normally (2-3 sentences + ONE equation)
- ALWAYS include page numbers with equations, examples, and figures
- Follow the EXACT order in the content - never jump ahead
- When introducing examples: ALL 4 steps in ONE response (mention Example number WITH PAGE, simplify problem, explain relevance, give choice)
- NEVER just ask "try it or walk through?" without mentioning Example number and explaining what it asks
- During walkthrough: Show ALL equations first, then EXTREMELY detailed steps
- RE-SHOW equations when using them (student should never scroll up)

⚠️ CRITICAL FINAL CHECKS BEFORE EACH RESPONSE:
1. Does this response follow the EXACT ORDER of the content? (Am I jumping ahead?)
2. Did I include page numbers for ALL equations, examples, and figures I mention?
3. Have I actually covered the prerequisites I claim to have covered?

If you're unsure about page numbers or order, CHECK THE CONTENT FIRST before responding!"""

    def start_teaching(self) -> str:
        """Start teaching with an opening question."""
        self.conversation_history = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "u\ser", "content": f"Start teaching me about {self.current_topic}. Ask me one simple opening question based on what's in the content."}
        ]
        
        response = self._call_llm()
        assistant_message = response["choices"][0]["message"]["content"]
        
        self.conversation_history.append({
            "role": "assistant",
            "content": assistant_message
        })
        
        return assistant_message
    
    def respond(self, user_message: str) -> str:
        """Continue the conversation."""
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        response = self._call_llm()
        assistant_message = response["choices"][0]["message"]["content"]
        
        self.conversation_history.append({
            "role": "assistant",
            "content": assistant_message
        })
        
        return assistant_message
    
    def _call_llm(self) -> Dict:
        """Call the LLM API."""
        response = requests.post(
            self.api_url,
            json={"messages": self.conversation_history},
            auth=self.auth,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        response.raise_for_status()
        return response.json()


def test_tutor():
    """Test the simplified tutor."""
    
    # Sample content (you can replace with actual section content)
    sample_content = """
    # Extracted Pages from modern_physics.pdf

    **Pages**: 47, 48, 49, 50, 51

    ---

    # Page 47

    ## 1-4 Time Dilation and Length Contraction

    straightforward and is accomplished as follows. The locus of points, e.g., with $x' = 1 \text{ m}$, is a line parallel to the $ct'$ axis through the point $x' = 1 \text{ m}, ct' = 0$, just as we saw earlier that the $ct'$ axis was the locus of those points with $x' = 0$ through the point $x' = 0, ct' = 0$. Substituting these values into the Lorentz transformation for $x'$, we see that the line through $x' = 1 \text{ m}$ intercepts the $x$ axis, i.e., the line where $ct = 0$ at

    $$
    x' = \gamma(x - vt) = \gamma(x - \beta ct) \quad \text{(1-24)}
    $$

    $$
    1 = \gamma x \quad \text{or} \quad x = 1/\gamma = \sqrt{1 - \beta^2}
    $$

    or, in general,

    $$
    x = x' \sqrt{1 - \beta^2}
    $$

    In Figure 1-22b, where $\beta = 0.5$, the line $x' = 1 \text{ m}$ intercepts the $x$ axis at $x = 0.866 \text{ m}$. Similarly, if $x' = 2 \text{ m}, x = 1.73 \text{ m}$; if $x' = 3 \text{ m}, x = 2.60 \text{ m}$; and so on.

    The $ct'$ axis is calibrated in a precisely equivalent manner. The locus of points with $ct' = 1 \text{ m}$ is a line parallel to the $x'$ axis through the point $ct' = 1 \text{ m}, x' = 0$. Using the Lorentz transformation, the intercept of that line with the $ct$ axis (where $x = 0$) is found as follows:

    $$
    t' = \gamma(t - vx/c^2)
    $$

    which can also be written as

    $$
    ct' = \gamma(ct - \beta x)
    $$

    or $ct' = \gamma ct$ for $x = 0$. Thus, for $ct' = 1 \text{ m}$, we have $1 = \gamma ct$ or $ct = (1 - \beta^2)^{1/2}$ and, again in general, $ct = ct'(1 - \beta^2)^{1/2}$. The $x' \cdot ct'$ coordinate grid is shown in Figure 1-22b.

    Notice in Figure 1-22b that the clocks located in $S'$ are *not* found to be synchronized by observers in $S$, even though they are synchronized in $S'$. This is exactly the conclusion that we arrived at in the discussion of the lightning striking the train and platform. In addition, those with positive $x'$ coordinates are behind the $S'$ reference clock and those with negative $x'$ coordinates are ahead, the differences being greatest for those clocks farthest away. This is a direct consequence of the Lorentz transformation of the time coordinate—i.e., when $ct = 0$ in Equation 1-25, $ct' = -\gamma \beta x$. Note, too, that the slope of the worldline of the light beam equals 1 in $S'$ as well as in $S$, as required by the second postulate.

    The results of correct measurements of the time and space intervals between events do not depend upon the kind of apparatus used for the measurements or on the events themselves. We are free therefore to choose any events and measuring apparatus that will help us understand the application of the Einstein postulates to the results of measurements. As you have already seen from previous examples, convenient events in relativity are those that produce light flashes. A convenient, simple such clock is a *light clock*, pictured schematically in Figure 1-24. A photocell detects the light pulse and sends a voltage pulse to an oscilloscope, which produces a vertical deflection of the oscilloscope's trace. The phosphorescent material on the face of the oscilloscope tube gives a persistent light that can be observed visually, photographed, or recorded electronically. The time between two light flashes is determined by measuring the 

    ## Figure Description
    The figure illustrates a light clock, which is a simple device used to measure time intervals based on the emission and detection of light pulses. It consists of a photocell that detects light pulses and sends voltage pulses to an oscilloscope. The oscilloscope displays a vertical deflection on its phosphorescent screen, allowing for visual observation, photography, or electronic recording of the light flashes. This setup enables the measurement of time intervals between successive light flashes.

    ## Figure
    ![Figure 1-24: A light clock, pictured schematically.](light-clock-illustration)

    ## No additional figures or content available on this page.

    ---

    # Page 48

    ## Chapter 1 Relativity I

    The page describes the concept of time intervals and time dilation in special relativity. 

    ## Light Clock

    The text explains that a light clock can be used to measure time intervals by reading the distance between pulses on an oscilloscope after calibrating the sweep speed.

    ## Equations

    The following equations are presented:

    $$
    L_1 = ct_1
    $$

    $$
    2L_2 = ct_2
    $$

    $$
    \Delta t = t_2 - t_1 = \frac{2L_2 - L_1}{c}
    $$

    ## Figure 1-24

    The diagram shows a light clock for measuring time intervals. The setup consists of a light source, a detector, a mirror, and an oscilloscope. The light travels from the source to the mirror and back to the detector, and the time interval is measured by reading the distance between pulses on the oscilloscope after calibrating the sweep speed.

    ![Figure 1-24: Light clock for measuring time intervals. The time is measured by reading the distance between pulses on the oscilloscope after calibrating the sweep speed.](light-clock-setup)

    ## Time Dilation (or Time Stretching)

    The text explains the concept of time dilation, considering an observer $A'$ at rest in frame $S'$ a distance $D$ from a mirror, also in $S'$. The observer triggers a flash gun and measures the time interval $\Delta t'$ between the original flash and the return flash from the mirror.

    ## Figure 1-25

    The diagrams show three parts: 
    - (a) illustrates observer $A'$ and the mirror in a spaceship at rest in frame $S'$. 
    - (b) presents the situation in frame $S$, where the spaceship is moving to the right with speed $v$. 
    - (c) shows a right triangle for computing the time $\Delta t$ in frame $S$. 

    The diagrams depict the path of light pulses from the flash gun to the mirror and back, with different configurations in the two frames $S'$ and $S$. 

    In diagram (a), $A'$ and the mirror are at rest in $S'$, and the light pulse travels a distance $2D$ to the mirror and back. 
    In diagram (b), the spaceship is moving to the right with speed $v$ in frame $S$, and the light pulse travels a longer distance due to the motion of the spaceship. 
    Diagram (c) shows a right triangle used to compute the time interval $\Delta t$ in frame $S$.

    ![Figure 1-25: (a) Observer $A'$ and the mirror are in a spaceship at rest in frame $S'$. The time it takes for the light pulse to reach the mirror and return is measured by $A'$ to be $2D/c$. (b) In frame $S$, the spaceship is moving to the right with speed $v$. If the speed of light is the same in both frames, the time it takes for the light to reach the mirror and return is longer than $2D/c$ in $S$ because the distance traveled is greater than $2D$. (c) A right triangle for computing the time $\Delta t$ in frame $S$.](spaceship-mirror-light-pulse)

    No callout boxes are present on this page.

    ---

    # Page 49

    ## 1-4 Time Dilation and Length Contraction

    In Figure 1-25b, a space diagram, we see that the path traveled by the light is longer in $S$ than in $S'$. However, by Einstein's postulates, light travels with the same speed $c$ in frame $S$ as it does in frame $S'$. Since it travels farther in $S$ at the same speed, it takes longer in $S$ to reach the mirror and return. The time interval between flashes in $S$ is thus longer than it is in $S'$. We can easily calculate $\Delta t$ in terms of $\Delta t'$. From the triangle in Figure 1-25c, we see that 

    $$
    \left(\frac{c\Delta t}{2}\right)^2 = D^2 + \left(\frac{v\Delta t}{2}\right)^2 \quad \text{(1-26)}
    $$

    or

    $$
    \Delta t = \frac{2D}{\sqrt{c^2 - v^2}} = \frac{2D}{c} \frac{1}{\sqrt{1 - v^2/c^2}} \quad \text{(1-26)}
    $$

    Using $\Delta t' = 2D/c$, we have

    $$
    \Delta t = \frac{\Delta t'}{\sqrt{1 - v^2/c^2}} = \gamma\Delta t' = \gamma\tau
    $$

    where $\tau = \Delta t'$ is the **proper time interval** that we first encountered in Example 1-3. Equation 1-26 describes **time dilation**; i.e., it tells us that the observer in frame $S$ always measures the time interval between two events to be longer (since $\gamma > 1$) than the corresponding interval measured on the clock located at both events in the frame where they occur at the same location. Thus, observers in $S$ conclude that the clock at $A'$ in $S'$ runs slow since that clock measures a smaller time interval between the two events. Notice that the faster $S'$ moves with respect to $S$, the larger is $\gamma$, and the slower the $S'$ clocks will tick. It appears to the $S$ observer that time is being stretched out in $S'$.

    Be careful! The **same clock** must be located at each event for $\Delta t'$ to be the proper time interval $\tau$. We can see why this is true by noting that Equation 1-26 can be obtained directly from the inverse Lorentz transformation for $t$. Referring again to Figure 1-25 and calling the emission of the flash event 1 and its return event 2, we have that

    $$
    \Delta t = t_2 - t_1 = \gamma\left(t_2' + \frac{vx_2'}{c^2}\right) - \gamma\left(t_1' + \frac{vx_1'}{c^2}\right)
    $$

    $$
    \Delta t = \gamma(t_2' - t_1') + \frac{\gamma v}{c^2}(x_2' - x_1')
    $$

    or

    $$
    \Delta t = \gamma\Delta t' + \frac{\gamma v}{c^2} \Delta x' \quad \text{(1-27)}
    $$

    If the clock that records $t_2'$ and $t_1'$ is located at the events, then $\Delta x' = 0$. If that is not the case, however, $\Delta x' \neq 0$ and $\Delta t'$, though certainly a valid measurement, is not a proper time interval. Only a clock located **at** an event when it occurs can record a proper time interval.

    ---

    # Page 50
    ## Chapter 1 Relativity I

    ## Example 1-7 Spatial Separation of Events
    Two events occur at the same point $x_0'$ at times $t_1'$ and $t_2'$ in $S'$, which moves with speed $v$ relative to $S$. What is the spatial separation of these events measured in $S$?

    ## Solution
    1. The location of the events in $S$ is given by the Lorentz inverse transformation Equation 1-19:
    $$
    x = \gamma(x' + vt') 
    $$

    2. The spatial separation of the two events $\Delta x = x_2 - x_1$ is then
    $$
    \Delta x = \gamma(x_0' + vt_2') - \gamma(x_0' + vt_1') 
    $$

    3. The $\gamma x_0'$ terms cancel:
    $$
    \Delta x = \gamma v(t_2' - t_1') = \gamma v \Delta t' 
    $$

    4. Since $\Delta t'$ is the proper time interval $\tau$, Equation 1-26 yields 
    $$
    \Delta x = v \gamma \tau = v \Delta t 
    $$

    5. Using the situation in Figure 1-26 as a numerical example, where $\beta = 0.5$ and $\gamma = 1.15$, we have 
    $$
    \Delta x = \gamma \frac{v}{c} \Delta (ct') = (1.15)(0.5)(2) = 1.15 \quad \text{m} 
    $$

    The spacetime diagram shows two reference frames, $S$ and $S'$, with their respective axes labeled $ct$ and $x$ for $S$, and $ct'$ and $x'$ for $S'$. The diagram illustrates time dilation, with a dashed line representing the worldline of a light flash emitted at $x' = 0$ and reflected back to that point by a mirror at $x' = 1$ m. The relative velocity between the frames results in different slopes for the axes. The diagram is used to visualize and derive the effects of special relativity, specifically time dilation and length contraction.

    ![Figure 1-26: Spacetime diagram illustrating time dilation. The dashed line is the worldline of a light flash emitted at $x' = 0$ and reflected back to that point by a mirror at $x' = 1$ m. $\beta = 0.5$.](spacetime-diagram-time-dilation)

    ## Example 1-8 The Pregnant Elephant
    Elephants have a gestation period of 21 months. Suppose that a freshly impregnated elephant is placed on a spaceship and sent toward a distant space jungle at $v = 0.75c$. If we monitor radio transmissions from the spaceship, how long after launch might we expect to hear the first squealing trumpet from the newborn calf?

    ## Solution
    1. In $S'$, the rest frame of the elephant, the time interval from launch to birth, is $\tau = 21$ months. In the Earth frame $S$ the time interval is $\Delta t_1$, given by Equation 1-26:
    $$
    \Delta t_1 = \gamma \tau = \frac{1}{\sqrt{1 - \beta^2}} \tau 
    $$
    $$
    = \frac{1}{\sqrt{1 - (0.75)^2}} (21 \text{ months}) 
    $$
    $$
    = 31.7 \text{ months} 
    $$

    2. At that time the radio signal announcing the happy event starts toward Earth at speed $c$, but from where? Using the result of Example 1-7, since launch the spaceship has moved $\Delta x$ in $S$, given by 
    $$
    \Delta x = \gamma vt = \gamma \beta ct 
    $$
    $$
    = (1.51)(0.75)(21 c \cdot \text{months}) 
    $$
    $$
    = 23.8 c \cdot \text{months} 
    $$
    where $c \cdot \text{month}$ is the distance light travels in one month.

    3. Notice that there is no need to convert $\Delta x$ into meters since our interest is in how long it will take the radio signal to travel this distance in $S$. That time is $\Delta t_2$, given by 
    $$
    \Delta t_2 = \Delta x / c 
    $$
    $$
    = 23.8 c \cdot \text{months} / c 
    $$
    $$
    = 23.8 \text{ months} 
    $$

    4. Thus, the good news will arrive at Earth at time $\Delta t$ after launch where 
    $$
    \Delta t = \Delta t_1 + \Delta t_2 
    $$
    $$
    = 31.7 + 23.8 
    $$
    $$
    = 55.5 \text{ months} 
    $$

    ---

    # Page 51

    ## 1-4 Time Dilation and Length Contraction

    Remarks: This result, too, is readily obtained from a spacetime diagram. Figure 1-27 illustrates the general appearance of the spacetime diagram for this example, showing the elephant's worldline and the worldline of the radio signal.

    ## Question

    8. You are standing on a corner and a friend is driving past in an automobile. Both of you note the times when the car passes two different intersections and determine from your watch readings the time that elapses between the two events. Which of you has determined the proper time interval?

    The time dilation of Equation 1-26 is easy to see in a spacetime diagram such as Figure 1-26, using the same round trip for a light pulse used above. Let the light flash leave $x' = 0$ at $ct' = 0$ when the $S$ and $S'$ origins coincided. The flash travels to $x' = 1$ m, reflects from a mirror located there, and returns to $x' = 0$. Let $\beta = 0.5$. The dotted line shows the worldline of the light beam, reflecting at $(x' = 1, ct' = 1)$ and returning to $x' = 0$ at $ct' = 2$ m. Note that the $S$ observer records the latter event at $ct > 2$ m; i.e., the observer in $S$ sees the $S'$ clock running slow.

    Experimental tests of the time dilation prediction have been performed using macroscopic clocks, in particular, accurate atomic clocks. In 1975, C. O. Alley conducted a test of both general and special relativity in which a set of atomic clocks were carried by a U.S. Navy antisubmarine patrol aircraft while it flew back and forth over the same path for 15 hours at altitudes between 8000 m and 10,000 m over Chesapeake Bay. The clocks in the plane were compared by laser pulses with an identical group of clocks on the ground. (See Figure 1-13 for one way such a comparison might be done.) Since the experiment was primarily intended to test the gravitational effect on clocks predicted by general relativity (see Section 2-5), the aircraft was deliberately flown at the rather sedate average speed of 270 knots $(140 \text{ m/s}) = 4.7 \times 10^{-7}c$ to minimize the time dilation due to the relative speeds of the clocks. Even so, after Alley deducted the effect of gravitation as predicted by general relativity, the airborne clocks lost an average of $5.6 \times 10^{-9}$ s due to the relative speed during the 15-hour flight. This result agrees with the prediction of special relativity, $5.7 \times 10^{-9}$ s, to within 2 percent, even at this low relative speed. The experimental results leave little basis for further debate as to whether traveling clocks of all kinds lose time on a round trip. They do.

    ## Length Contraction

    A phenomenon closely related to time dilation is length contraction. The length of an object measured in the reference frame in which the object is at rest is called its proper length $L_p$. In a reference frame in which the object is moving, the measured length parallel to the direction of motion is shorter than its proper length. Consider a rod at rest in the frame $S'$ with one end at $x_1'$ and the other end at $x_2'$, as illustrated in Figure 1-28. The length of the rod in this frame is its proper length $L_p = x_2' - x_1'$. Some care must

    The spacetime diagram for Example 1-8 is shown in Figure 1-27. The diagram illustrates the worldline of a pregnant elephant and a radio signal. The worldline of the elephant is represented by a colored line, and the worldline of the radio signal is depicted as a dashed line at a 45-degree angle towards the upper left. The diagram also includes labels for $ct$ and $x$ axes, with units given in $c \cdot \text{mo}$.

    ![Figure 1-27: Sketch of the spacetime diagram for Example 1-8. $\beta = 0.75$. The colored line is the worldline of the pregnant elephant. The worldline of the radio signal is the dashed line at $45^\circ$ toward the upper left.](figure-1-27-sketch-spacetime-diagram-example-1-8)

    Figure 1-28 shows a measuring rod, specifically a meter stick, at rest in frame $S'$, with one end at $x_1' = 1$ m and the other end at $x_2' = 2$ m. The frame $S'$, with $\beta = 0.79$ relative to $S$, is in motion. To measure the length of the rod in frame $S$, the locations of the rod's ends, $x_2$ and $x_1$, must be determined simultaneously. Direct measurement from the diagram yields $L/L_p = 0.61 = 1/\gamma$.

    The detailed description of Figure 1-28 is as follows: The diagram depicts a measuring rod or meter stick in frame $S'$, with its ends at $x_1' = 1$ m and $x_2' = 2$ m. Frame $S'$ is moving with $\beta = 0.79$ relative to frame $S$. The worldlines of the ends of the rod are shown, and the length of the rod in frame $S$ is measured to be $L$, which is obviously shorter than its proper length $L_p$. 

    ![Figure 1-28: A measuring rod, a meter stick in this case, lies at rest in $S'$ between $x_2' = 2$ m and $x_1' = 1$ m. System $S'$ moves with $\beta = 0.79$ relative to $S$. Since the rod is in motion, $S$ must measure the locations of the ends of the rod $x_2$ and $x_1$ simultaneously in order to have made a valid length measurement. $L$ is obviously shorter than $L_p$. By direct measurement from the diagram (use a millimeter scale) $L/L_p = 0.61 = 1/\gamma$.](figure-1-28-measuring-rod)
"""
    
    # Initialize tutor
    api_url = "https://smapi-int-tsta.bcbsfl.com/gpt/api/v1/models/meta-llama/Llama-4-Scout-17B-16E-Instruct/v1/chat/completions"
    # api_url = "https://smapi-int-tsta.bcbsfl.com/gpt/api/v1/models/meta-llama/Llama-3.2-90B-Vision-Instruct-vllm/v1/chat/completions"
    username = "m8yl"
    password = "Fl33ll66"
    
    tutor = SimpleSocraticTutor(api_url, username, password)
    tutor.set_section_content(sample_content, "Time dialation and Length contraction")
    
    print("="*80)
    print("SIMPLE SOCRATIC TUTOR - Testing")
    print("="*80)
    print(f"\nTeaching: {tutor.current_topic}")
    print("Keep responses SHORT - one concept/equation per turn!\n")
    print("-"*80)
    
    # Start teaching
    opening = tutor.start_teaching()
    print(f"Tutor: {opening}\n")
    print("-"*80)
    
    # Interactive loop
    while True:
        user_input = input("\nYou: ").strip()
        
        if user_input.lower() in ['quit', 'exit', 'done']:
            print("\nSession ended.")
            break
        
        if not user_input:
            continue
        
        print("\n🤔 Thinking...")
        response = tutor.respond(user_input)
        print(f"\nTutor: {response}\n")
        print("-"*80)


if __name__ == "__main__":
    test_tutor()
