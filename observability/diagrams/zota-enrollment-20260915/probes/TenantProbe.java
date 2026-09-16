import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.util.Map;
import jakarta.persistence.EntityManager;
import org.eclipse.zota.context.AccessContext;
import org.eclipse.zota.enrollment.jpa.TargetEnrollmentManagement;
import org.eclipse.zota.repository.jpa.model.JpaTarget;
import org.eclipse.zota.repository.jpa.repository.TargetRepository;
import org.h2.jdbcx.JdbcDataSource;
import org.h2.tools.RunScript;
import org.mockito.Mockito;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.orm.jpa.SharedEntityManagerCreator;
import org.springframework.orm.jpa.vendor.EclipseLinkJpaVendorAdapter;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.transaction.support.TransactionTemplate;

// Tests the real EclipseLink/JPA tenant boundary; no deployed database or network.
public class TenantProbe {
    public static void main(String[] args) throws Exception {
        JdbcDataSource ds = new JdbcDataSource();
        ds.setURL("jdbc:h2:mem:enrollment_tenant;DB_CLOSE_DELAY=-1");
        ds.setUser("sa");
        try (var c = ds.getConnection();
             var sql = Files.newBufferedReader(Path.of(args[0]))) {
            RunScript.execute(c, sql);
            c.createStatement().executeUpdate("""
                    INSERT INTO sp_target
                    (tenant,name,controller_id,sec_token,request_controller_attributes,update_status,
                     created_by,created_at,last_modified_by,last_modified_at,optlock_revision)
                    VALUES ('DEFAULT','review','REVIEW-VIN','synthetic-target',false,0,'review',1,'review',1,0)
                    """);
        }
        var factory = new LocalContainerEntityManagerFactoryBean();
        factory.setDataSource(ds);
        factory.setJpaVendorAdapter(new EclipseLinkJpaVendorAdapter());
        factory.setPackagesToScan("org.eclipse.zota.repository.jpa.model");
        factory.setJpaPropertyMap(Map.of(
                "eclipselink.weaving", "false", "eclipselink.logging.level", "SEVERE",
                "eclipselink.ddl-generation", "none"));
        factory.afterPropertiesSet();
        try {
            var constructor = Class.forName("org.eclipse.zota.repository.jpa.TransactionManager")
                    .getDeclaredConstructor();
            constructor.setAccessible(true);
            var tm = (JpaTransactionManager) constructor.newInstance();
            tm.setEntityManagerFactory(factory.getObject());
            tm.afterPropertiesSet();
            var tx = new TransactionTemplate(tm);
            tx.setReadOnly(true);
            EntityManager em = SharedEntityManagerCreator.createSharedEntityManager(factory.getObject());
            var targetRepo = Mockito.mock(TargetRepository.class);
            Mockito.when(targetRepo.findByControllerId("REVIEW-VIN")).thenAnswer(invocation ->
                    em.createQuery("SELECT t FROM JpaTarget t WHERE t.controllerId = :vin", JpaTarget.class)
                            .setParameter("vin", "REVIEW-VIN").getResultStream().findFirst());
            var management = new TargetEnrollmentManagement(
                    null, null, targetRepo, null, null, null, Clock.systemUTC());

            SecurityContextHolder.clearContext();
            try {
                tx.executeWithoutResult(status ->
                        management.verifyTargetToken("DEFAULT", "REVIEW-VIN", "synthetic-target"));
                throw new AssertionError("Expected missing tenant in pre-authentication transaction");
            } catch (RuntimeException expected) {
                Throwable root = expected;
                while (root.getCause() != null) root = root.getCause();
                System.out.println("PROBE CURRENT tenant-after-transaction: " + root.getMessage());
            }
            AccessContext.asSystemAsTenant("DEFAULT", () -> tx.executeWithoutResult(status ->
                    management.verifyTargetToken("DEFAULT", "REVIEW-VIN", "synthetic-target")));
            System.out.println("PROBE CONTROL tenant-before-transaction: PASS");
        } finally {
            factory.destroy();
            SecurityContextHolder.clearContext();
        }
    }
}
