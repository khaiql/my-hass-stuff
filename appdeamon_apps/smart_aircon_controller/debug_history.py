import appdaemon.plugins.hass.hassapi as hass
import json
from pprint import pformat


class DebugHistory(hass.Hass):
    """
    Debug script to test get_history method with different parameters
    and understand the data structure returned.
    """

    def initialize(self):
        """Initialize the debug script."""
        self.log("=== DEBUG HISTORY SCRIPT STARTING ===")
        
        # Test entity - change this to match your setup
        test_entity = self.args.get("test_entity", "climate.aircon")
        
        # Run the debug tests after a short delay to ensure HA is ready
        self.run_in(self.run_debug_tests, 5, entity_id=test_entity)

    def run_debug_tests(self, kwargs):
        """Run various get_history tests."""
        entity_id = kwargs.get("entity_id")
        
        self.log(f"🔍 Testing get_history for entity: {entity_id}")
        self.log("=" * 60)
        
        # Test 1: Basic call with days parameter
        self.test_history_days(entity_id, 1)
        
        # Test 2: Different days parameter
        self.test_history_days(entity_id, 2)
        
        # Test 3: Last 1 hour using start_time
        self.test_history_last_hour(entity_id)
        
        # Test 4: With start_time parameter (if supported)
        self.test_history_with_start_time(entity_id)
        
        self.log("=" * 60)
        self.log("🏁 DEBUG HISTORY SCRIPT COMPLETED")

    def test_history_days(self, entity_id, days):
        """Test get_history with days parameter."""
        self.log(f"\n📅 TEST: get_history(entity_id='{entity_id}', days={days})")
        
        try:
            history = self.get_history(entity_id=entity_id, days=days)
            self.log(f"✅ SUCCESS: get_history returned")
            self.analyze_history_data(history, f"days={days}")
            
        except Exception as e:
            self.log(f"❌ ERROR: get_history with days={days} failed: {e}")

    def test_history_last_hour(self, entity_id):
        """Test get_history for the last 1 hour using start_time parameter."""
        self.log(f"\n⏰ TEST: get_history for last 1 hour (entity_id='{entity_id}')")
        
        try:
            import datetime
            # Get history for the last 1 hour
            start_time = datetime.datetime.now() - datetime.timedelta(hours=1)
            end_time = datetime.datetime.now()
            
            # Test with just start_time
            self.log(f"   Testing with start_time only (1 hour ago): {start_time}")
            history = self.get_history(entity_id=entity_id, start_time=start_time)
            self.log(f"✅ SUCCESS: get_history with start_time (1 hour ago) returned")
            self.analyze_history_data(history, f"start_time=1_hour_ago")
            
            # Test with both start_time and end_time
            self.log(f"   Testing with start_time and end_time: {start_time} to {end_time}")
            history = self.get_history(entity_id=entity_id, start_time=start_time, end_time=end_time)
            self.log(f"✅ SUCCESS: get_history with start_time and end_time returned")
            self.analyze_history_data(history, f"start_time_and_end_time=1_hour_window")
            
        except Exception as e:
            self.log(f"❌ ERROR: get_history for last 1 hour failed: {e}")

    def test_history_with_start_time(self, entity_id):
        """Test get_history with start_time parameter."""
        self.log(f"\n🕐 TEST: get_history with start_time")
        
        try:
            import datetime
            # Test with start time 24 hours ago
            start_time = datetime.datetime.now() - datetime.timedelta(hours=24)
            
            history = self.get_history(entity_id=entity_id, start_time=start_time)
            self.log(f"✅ SUCCESS: get_history with start_time returned")
            self.analyze_history_data(history, f"start_time={start_time}")
            
        except Exception as e:
            self.log(f"❌ ERROR: get_history with start_time failed: {e}")

    def analyze_history_data(self, history, test_params):
        """Analyze and log the structure of history data."""
        self.log(f"📊 ANALYSIS for {test_params}:")
        
        # Basic type and structure
        self.log(f"   Type: {type(history)}")
        
        if history is None:
            self.log("   Result: None")
            return
            
        if isinstance(history, list):
            self.log(f"   Length: {len(history)}")
            
            if len(history) > 0:
                first_item = history[0]
                self.log(f"   First item type: {type(first_item)}")
                
                if isinstance(first_item, list):
                    self.log(f"   First item length: {len(first_item)}")
                    
                    if len(first_item) > 0:
                        sample_entry = first_item[0]
                        self.log(f"   Sample entry type: {type(sample_entry)}")
                        
                        if hasattr(sample_entry, '__dict__'):
                            # If it's an object with attributes
                            self.log(f"   Sample entry attributes: {dir(sample_entry)}")
                        elif isinstance(sample_entry, dict):
                            # If it's a dictionary
                            self.log(f"   Sample entry keys: {list(sample_entry.keys())}")
                            # Print a few key values
                            for key in ['entity_id', 'state', 'last_changed', 'last_updated']:
                                if key in sample_entry:
                                    value = sample_entry[key]
                                    self.log(f"   {key}: {value} (type: {type(value)})")
                        
                        # Print the first few entries for detailed inspection
                        if len(first_item) >= 1:
                            self.log(f"   📝 DETAILED SAMPLE (first entry):")
                            self.log(f"      {pformat(self.safe_dict_conversion(sample_entry), width=120)}")
                            
                        if len(first_item) >= 2:
                            self.log(f"   📝 DETAILED SAMPLE (second entry):")
                            second_entry = first_item[1]
                            self.log(f"      {pformat(self.safe_dict_conversion(second_entry), width=120)}")
                else:
                    self.log(f"   First item: {first_item}")
        else:
            self.log(f"   Unexpected history type: {type(history)}")
            self.log(f"   Content: {history}")
            
        self.log("")  # Add blank line for readability

    def safe_dict_conversion(self, obj):
        """Safely convert object to dictionary for printing."""
        if isinstance(obj, dict):
            return obj
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        else:
            return str(obj) 