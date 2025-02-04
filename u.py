from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import requests
import json
import os

class LLMTestGenerator:
    def __init__(self, api_key, site_url, site_name):
        self.api_key = api_key
        self.site_url = site_url
        self.site_name = site_name
        
    def generate_test_case(self, elements_data, user_prompt):
        """Generate a test case using the LLM based on detected elements and user prompt"""
        # Format the elements data for the LLM
        elements_description = self._format_elements_data(elements_data)
        
        # Construct the prompt
        prompt = f"""You are a test automation expert. Given the following web elements and user requirements, generate a test case that follows the exact JSON structure shown below.

Available Elements:
{elements_description}

User Requirements:
{user_prompt}

Response must be a valid JSON object with this exact structure:
{{
    "steps": [
        {{
            "action": "find_element",
            "by": "xpath",
            "value": "//specific/xpath/here",
            "step_type": "input",
            "input_value": "actual value to input"
        }}
    ]
}}

Rules:
1. Response must be ONLY the JSON object, no additional text
2. Each step must have all fields shown above
3. For inputs, use realistic values within normal boundaries
4. For EMI calculators: loan amount (10000-10000000), interest rate (5-15), tenure (12-360 months)
5. Use proper XPath values from the available elements

Example response:
{{
    "steps": [
        {{
            "action": "find_element",
            "by": "xpath",
            "value": "//input[@placeholder='Amount']",
            "step_type": "input",
            "input_value": "2500000"
        }}
    ]
}}"""

        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": self.site_url,
                    "X-Title": self.site_name,
                },
                data=json.dumps({
                    "model": "deepseek/deepseek-r1-distill-llama-70b",
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
                    raise Exception(f"Invalid test case format: {str(e)}")
            else:
                raise Exception(f"API request failed with status code: {response.status_code}")
                
        except Exception as e:
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
        
        # Try to find Chrome binary location
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
            self.driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            print(f"Error initializing Chrome driver: {str(e)}")
            print("\nPlease make sure Chrome and ChromeDriver are installed:")
            print("1. Install Chrome browser if not already installed")
            print("2. Install ChromeDriver via Homebrew: brew install chromedriver")
            print("3. If using macOS, you might need to allow ChromeDriver in System Settings > Security & Privacy")
            raise
        self.elements_data = {}
        
    def detect_elements(self, url):
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
            
            return self.elements_data
            
        except Exception as e:
            print(f"Error during element detection: {str(e)}")
            raise

    def _generate_xpath(self, element):
        """Generate a unique XPath for the element"""
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
        self.driver.quit()

class TestExecutor:
    def __init__(self):
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--start-maximized')
        
        # Try to find Chrome binary location
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
            self.driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            print(f"Error initializing Chrome driver: {str(e)}")
            print("\nPlease make sure Chrome and ChromeDriver are installed:")
            print("1. Install Chrome browser if not already installed")
            print("2. Install ChromeDriver via Homebrew: brew install chromedriver")
            print("3. If using macOS, you might need to allow ChromeDriver in System Settings > Security & Privacy")
            raise
    
    def execute_test(self, url, test_steps):
        """Execute a test case generated by the LLM"""
        try:
            print("Starting test execution...")
            self.driver.get(url)
            
            for step in test_steps['steps']:
                element = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, step['value']))
                )
                
                if step['step_type'] == 'input':
                    element.clear()
                    element.send_keys(step['input_value'])
                    print(f"Entered '{step['input_value']}' into element: {step['value']}")
                    
                elif step['step_type'] == 'click':
                    element.click()
                    print(f"Clicked element: {step['value']}")
                    
                elif step['step_type'] == 'select':
                    from selenium.webdriver.support.ui import Select
                    select = Select(element)
                    select.select_by_visible_text(step['input_value'])
                    print(f"Selected '{step['input_value']}' from element: {step['value']}")
            
            print("Test completed successfully")
            return True, "Test executed successfully"
            
        except Exception as e:
            print(f"Test execution failed: {str(e)}")
            return False, f"Test execution failed: {str(e)}"
        
    def close(self):
        self.driver.quit()

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
        
    url = "https://www.dbs.com/digibank/in/loans/calculators/home-loan-emi-calculator.page"
    
    try:
        # First detect elements
        print("Starting element detection...")
        detector = ElementDetector()
        elements = detector.detect_elements(url)
        detector.close()
        
        # Get user prompt
        user_prompt = input("\nWhat kind of test case would you like to generate? Describe the scenario: ")
        
        # Generate test case using LLM
        print("\nGenerating test case...")
        generator = LLMTestGenerator(api_key, site_url, site_name)
        test_case = generator.generate_test_case(elements, user_prompt)
        
        # Execute generated test
        print("\nStarting test execution...")
        executor = TestExecutor()
        success, message = executor.execute_test(url, test_case)
        executor.close()
        
        print(f"\nTest execution result: {message}")
        
    except Exception as e:
        print(f"Error in main: {str(e)}")

if __name__ == "__main__":
    main()