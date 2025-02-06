from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import TimeoutException
import requests
import json
import os
import base64
import time

class LLMTestGenerator:
    def __init__(self, api_key, site_url, site_name):
        self.api_key = api_key
        self.site_url = site_url
        self.site_name = site_name
        
    def generate_test_case(self, elements_data, user_prompt, screenshot_path=None):
        """Generate a test case using the LLM based on detected elements, user prompt, and optional screenshot."""
        # Format the elements data for the LLM
        elements_description = self._format_elements_data(elements_data)
        
        # Include screenshot reference in the prompt if available
        screenshot_note = "A screenshot of the page has been captured and is available for reference." if screenshot_path else ""
        
        # Construct the prompt
        prompt = f"""You are a test automation expert. Given the following web elements, {screenshot_note} and user requirements, generate a test case that follows the exact JSON structure shown below.But do not be limited to that, you need to add complex functionality for clicking buttons, scrolling, dropdowns, date, etc. Although, the response should ONLY be a JSON object otherwise it will be an error. In case of phone number, do not touch the country code, only input a 10 digit indian number.

Available Elements:
{elements_description}

User Requirements:
{user_prompt}

Response must be a valid JSON object with this exact structure, with input as optional but others mandatory:
{{
    "steps": [
        {{
            "action": "find_element",
            "by": "xpath",
            "value": "//specific/xpath/here",
            "step_type": "input|click|select|scroll",
            "input_value": "actual value (only for input/select)"
        }}
    ]
}}

For this use case:
1. click on name input element
2. input name
3. click on DOB input element
4. input DOB in DD/MM/YYYY format
5. Click on email input element
6. input email id
7. Click on the enter mobile number input element (ends with div[2]/input[1]), it will not be clickable and other element will receive the click but it's okay, keep it going.
8. input 10 digit phone number 9723670332
9. check the consent box
10. click on calculate premium button

Rules:
1. ONLY respond with valid JSON
2. Include 'input_value' ONLY for input/select steps
3. Use realistic values matching element purposes
4. For scroll actions, scroll to element before interacting if needed
5. Use XPaths from detected elements"""

        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": self.site_url,
                    "X-Title": self.site_name,
                },
                data=json.dumps({
                    "model": "qwen/qwen-turbo",
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                })
            )
            
            if response.status_code == 200:
                content = response.json()['choices'][0]['message']['content']
                print(f"JSON response from LLM: {content}")
                try:
                    # Try to clean the content in case there's any extra text
                    content = content.strip()
                    if content.startswith('```json'):
                        content = content[7:]
                    if content.endswith('```'):
                        content = content[:-3]
                    content = content.strip()
                    
                    # Parse the JSON
                    test_case = json.loads(content)
                    
                    # Validate structure
                    if not isinstance(test_case, dict) or 'steps' not in test_case:
                        raise ValueError("Invalid test case structure")
                    
                    for step in test_case['steps']:
                        required_fields = ['action', 'by', 'value', 'step_type']
                        if not all(field in step for field in required_fields):
                            raise ValueError(f"Step missing required fields: {required_fields}")
                    
                    return test_case
                    
                except json.JSONDecodeError as e:
                    print(f"Invalid JSON response from LLM: {content}")
                    raise Exception(f"Failed to parse LLM response as JSON: {str(e)}")
                except Exception as e:
                    print(f"JSON response from LLM: {content}")
                    raise Exception(f"Invalid test case format: {str(e)}")
            else:
                raise Exception(f"API request failed with status code: {response.status_code}")
                
        except Exception as e:
            # print(f"JSON response from LLM: {content}")
            raise Exception(f"Error generating test case: {str(e)}")
    
    def _format_elements_data(self, elements_data):
        """Format the elements data into a readable string for the LLM"""
        formatted = []
        for element_type, elements in elements_data.items():
            formatted.append(f"\n{element_type.upper()} Elements:")
            for elem in elements:
                attributes = [f"{k}: {v}" for k, v in elem.items() if v]
                formatted.append("  - " + ", ".join(attributes))
        return "\n".join(formatted)

class ElementDetector:
    def __init__(self):
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--start-maximized')
        chrome_options.add_argument('--headless=new')  # Run in headless mode for detection
        self.driver = self._init_driver(chrome_options)
        self.elements_data = {}
        
    def _init_driver(self, chrome_options):
        """Initialize the Chrome driver with the given options."""
        chrome_paths = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',  # macOS
            '/usr/bin/google-chrome',  # Linux
            '/usr/bin/chromium',  # Linux Chromium
            'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',  # Windows
        ]
        
        for path in chrome_paths:
            if os.path.exists(path):
                chrome_options.binary_location = path
                break
        
        try:
            return webdriver.Chrome(options=chrome_options)
        except Exception as e:
            print(f"Error initializing Chrome driver: {str(e)}")
            print("\nPlease make sure Chrome and ChromeDriver are installed:")
            print("1. Install Chrome browser if not already installed")
            print("2. Install ChromeDriver via Homebrew: brew install chromedriver")
            print("3. If using macOS, you might need to allow ChromeDriver in System Settings > Security & Privacy")
            raise
    
    def detect_elements(self, url):
        """Detect elements on the page and capture a screenshot."""
        try:
            print(f"Navigating to URL: {url}")
            self.driver.get(url)
            
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except TimeoutException:
                print("Page load timeout, but continuing with element detection...")
            
            print(f"Current URL: {self.driver.current_url}")

            # Capture screenshot
            screenshot_path = "page_screenshot.png"
            self.driver.save_screenshot(screenshot_path)
            print(f"Screenshot saved to {screenshot_path}")

            # Detect elements
            element_types = {
                'input': '//input',
                'button': '//button',
                'select': '//select',
                'link': '//a',
            }
            
            for element_type, xpath in element_types.items():
                print(f"Looking for {element_type} elements...")
                elements = self.driver.find_elements(By.XPATH, xpath)
                self.elements_data[element_type] = []
                
                for element in elements:
                    element_info = {
                        'type': element_type,
                        'id': element.get_attribute('id'),
                        'name': element.get_attribute('name'),
                        'class': element.get_attribute('class'),
                        'text': element.text if element.text else element.get_attribute('value'),
                        'xpath': self._generate_xpath(element)
                    }
                    self.elements_data[element_type].append(element_info)
                    print(f"Found {element_type}: {element_info}")
            
            return self.elements_data, screenshot_path
            
        except Exception as e:
            print(f"Error during element detection: {str(e)}")
            raise

    def _generate_xpath(self, element):
        """Generate a unique XPath for the element."""
        try:
            script = """
            function getXPath(element) {
                if (element.id !== '')
                    return `//*[@id="${element.id}"]`;
                
                if (element === document.body)
                    return element.tagName.toLowerCase();

                var ix = 0;
                var siblings = element.parentNode.childNodes;
                
                for (var i = 0; i < siblings.length; i++) {
                    var sibling = siblings[i];
                    
                    if (sibling === element)
                        return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                    
                    if (sibling.nodeType === 1 && sibling.tagName === element.tagName)
                        ix++;
                }
            }
            return getXPath(arguments[0]);
            """
            return self.driver.execute_script(script, element)
        except:
            return None
        
    def close(self):
        """Close the browser."""
        self.driver.quit()

class TestExecutor:
    def __init__(self):
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--start-maximized')
        self.driver = self._init_driver(chrome_options)
    
    def _init_driver(self, chrome_options):
        """Initialize the Chrome driver with the given options."""
        chrome_paths = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',  # macOS
            '/usr/bin/google-chrome',  # Linux
            '/usr/bin/chromium',  # Linux Chromium
            'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',  # Windows
        ]
        
        for path in chrome_paths:
            if os.path.exists(path):
                chrome_options.binary_location = path
                break
        
        try:
            return webdriver.Chrome(options=chrome_options)
        except Exception as e:
            print(f"Error initializing Chrome driver: {str(e)}")
            print("\nPlease make sure Chrome and ChromeDriver are installed:")
            print("1. Install Chrome browser if not already installed")
            print("2. Install ChromeDriver via Homebrew: brew install chromedriver")
            print("3. If using macOS, you might need to allow ChromeDriver in System Settings > Security & Privacy")
            raise
    
    def execute_test(self, url, test_steps):
        """Execute a test case generated by the LLM."""
        try:
            print("Starting test execution...")
            self.driver.get(url)
            
            for step in test_steps['steps']:
                element = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, step['value']))
                )

                # Handle different action types
                if step['step_type'] == 'input':
                    element.clear()
                    element.send_keys(step['input_value'])
                    print(f"Entered '{step['input_value']}' into element: {step['value']}")
                    
                elif step['step_type'] == 'click':
                    element.click()
                    print(f"Clicked element: {step['value']}")
                    
                elif step['step_type'] == 'select':
                    Select(element).select_by_visible_text(step['input_value'])
                    print(f"Selected '{step['input_value']}' from element: {step['value']}")
                    
                elif step['step_type'] == 'scroll':
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                        element
                    )
                    # Add visual feedback for scroll action
                    self.driver.execute_script(
                        "arguments[0].style.border = '3px solid red';",
                        element
                    )
                    print(f"Scrolled to element: {step['value']}")
            
            print("Test execution completed successfully - browser remains open")
            time.sleep(300)
            return True, "Test executed successfully"
            
        except Exception as e:
            print(f"Test execution failed: {str(e)}")
            return False, f"Test execution failed: {str(e)}"
        
    def close(self):
        """No-op to keep browser open."""
        pass

def main():
    # Get API credentials from user input if not in environment variables
    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        api_key = "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"
    
    site_url = os.getenv('SITE_URL')
    if not site_url:
        site_url = "<YOUR_SITE_URL>"
    
    site_name = os.getenv('SITE_NAME')
    if not site_name:
        site_name = "<YOUR_SITE_URL>"
        
    url = "https://www.tataaia.com/campaign/TATA-AIA-Life-Insurance-Term-Plan-Calculator-Sampoorn-Raksha-Promise.html"
    
    try:
        # First detect elements
        print("Starting element detection...")
        detector = ElementDetector()
        elements, screenshot_path = detector.detect_elements(url)
        detector.close()
        
        # Get user prompt
        user_prompt = input("\nWhat kind of test case would you like to generate? Describe the scenario: ")
        # Generate test case using LLM
        print("\nGenerating test case...")
        generator = LLMTestGenerator(api_key, site_url, site_name)
        test_case = generator.generate_test_case(elements, user_prompt, screenshot_path)
        
        # Execute generated test
        print("\nStarting test execution...")
        executor = TestExecutor()
        success, message = executor.execute_test(url, test_case)
        
        print(f"\nTest execution result: {message}")
        
    except Exception as e:
        print(f"Error in main: {str(e)}")

if __name__ == "__main__":
    main()