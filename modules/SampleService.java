cat << 'EOF' > modules/SampleService.java
package com.example;

public class SampleService {
    private String apiKey;

    public boolean processPayment(double amount) {
        System.out.println("Processing payment of " + amount);
        return true;
    }
}
EOF