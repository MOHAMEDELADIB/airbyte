package io.airbyte.integrations.destination.mysql;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.spy;

import com.fasterxml.jackson.databind.JsonNode;
import com.google.common.collect.ImmutableMap;
import io.airbyte.commons.json.Jsons;
import java.util.Map.Entry;
import org.junit.jupiter.api.Test;

public class MySQLDestinationTest {

  private MySQLDestination getDestination() {
    final MySQLDestination result = spy(MySQLDestination.class);
    return result;
  }

  private JsonNode buildConfigNoJDBCParameters() {
    final JsonNode config = Jsons.jsonNode(ImmutableMap.of(
        "host", "localhost",
        "port", 1337,
        "username", "user",
        "database", "db"
    ));
    return config;
  }

  private JsonNode buildConfigWithExtraJDBCParameters(final String extraParam) {
    final JsonNode config = Jsons.jsonNode(ImmutableMap.of(
        "host", "localhost",
        "port", 1337,
        "username", "user",
        "database", "db",
        "jdbc_url_params", extraParam
    ));
    return config;
  }

  private JsonNode buildConfigWithExtraJDBCParametersNoSSL(final String extraParam) {
    final JsonNode config = Jsons.jsonNode(ImmutableMap.of(
        "host", "localhost",
        "port", 1337,
        "username", "user",
        "database", "db",
        "ssl", false,
        "jdbc_url_params", extraParam
    ));
    return config;
  }

  @Test
  void testNoExtraParams() {
    final JsonNode jdbcConfig = getDestination().toJdbcConfig(buildConfigNoJDBCParameters());
    final String url = jdbcConfig.get("jdbc_url").asText();
    assertEquals("jdbc:mysql://localhost:1337/db?zeroDateTimeBehavior=convertToNull&useSSL=true&requireSSL=true&verifyServerCertificate=false&", url);
  }

  @Test
  void testEmptyExtraParams() {
    final JsonNode jdbcConfig = getDestination().toJdbcConfig(buildConfigWithExtraJDBCParameters(""));
    final String url = jdbcConfig.get("jdbc_url").asText();
    assertEquals("jdbc:mysql://localhost:1337/db?zeroDateTimeBehavior=convertToNull&useSSL=true&requireSSL=true&verifyServerCertificate=false&", url);
  }

  @Test
  void testExtraParams() {
    final String extraParam = "key1=value1&key2=value2&key3=value3";
    final JsonNode jdbcConfig = getDestination().toJdbcConfig(buildConfigWithExtraJDBCParameters(extraParam));
    final String url = jdbcConfig.get("jdbc_url").asText();
    assertEquals(
        "jdbc:mysql://localhost:1337/db?zeroDateTimeBehavior=convertToNull&key1=value1&key2=value2&key3=value3&useSSL=true&requireSSL=true&verifyServerCertificate=false&",
        url);
  }

  @Test
  void testExtraParamsWithSSLParameter() {
    for (final Entry<String, String> entry : MySQLDestination.getSSLParameters().entrySet()) {
      final String extraParam = MySQLDestination.formatParameter(entry.getKey(), entry.getValue());
      assertThrows(RuntimeException.class, () ->
          getDestination().toJdbcConfig(buildConfigWithExtraJDBCParameters(extraParam))
      );
    }
  }

  @Test
  void testExtraParamsWithSSLParameterNoSSL() {
    for (final Entry<String, String> entry : MySQLDestination.getSSLParameters().entrySet()) {
      final String extraParam = MySQLDestination.formatParameter(entry.getKey(), entry.getValue());
      final JsonNode jdbcConfig = getDestination().toJdbcConfig(buildConfigWithExtraJDBCParametersNoSSL(extraParam));
      final String url = jdbcConfig.get("jdbc_url").asText();
      final String expected = String.format("jdbc:mysql://localhost:1337/db?zeroDateTimeBehavior=convertToNull&%s&", extraParam);
      assertEquals(expected,
          url);
    }
  }
}
